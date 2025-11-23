import os
import json
import base64
import requests
import sentry_sdk
from groq import Groq
from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
SENTRY_DSN = "https://93f0c27a3a4f4a9b26fbbe83b2b3be6d@o4510413108477952.ingest.us.sentry.io/4510413862862848"
TELNYX_API_KEY = os.getenv("TELNYX_API_KEY")
TELNYX_PHONE_NUMBER = os.getenv("TELNYX_PHONE_NUMBER")
ADMIN_PHONE_NUMBER = os.getenv("ADMIN_PHONE_NUMBER")
TELNYX_CONNECTION_ID = "2834931739384612416"  # your existing connection id
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

TELNYX_BASE_URL = "https://api.telnyx.com/v2"
TELNYX_HEADERS = {
    "Authorization": f"Bearer {TELNYX_API_KEY}",
    "Content-Type": "application/json"
}

# --- GLOBAL STATE (Agent + Frontend Sync) ---
CURRENT_STATE = {
    "status": "IDLE",           # IDLE | ANALYZING | BLOCKED_AWAITING_AUTH | QNA_MODE | APPROVED | DECLINED
    "risk_score": 0,
    "analysis": "System Ready",
    "last_digit": None,         # last key pressed (for frontend display)
    "last_question": None,      # last voice question
    "last_answer": None         # last LLM answer
}

# Store the last transaction so Groq can answer about it
LAST_TRANSACTION = {
    "action": None,
    "payload": None,
    "reasoning": None
}

if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=1.0, send_default_pii=True)

groq_client = Groq(api_key=GROQ_API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ActionRequest(BaseModel):
    agent_id: str
    action: str
    payload: dict
    reasoning: str

# --- AI RISK ANALYSIS WITH GROQ ---

def analyze_risk_with_groq(action, payload, reasoning):
    print("⚡ [GROQ] Analyzing Risk with Llama 3.3...")
    try:
        prompt = f"""
        You are a Financial Security AI. Analyze this transaction request.
        Context:
        - Action: {action}
        - Details: {json.dumps(payload)}
        - Reasoning: "{reasoning}"

        Rules:
        - Payment > $5,000 to "Unknown" vendors is CRITICAL RISK (Score 90-100).
        - Payment 1,000–5,000 to unknown vendors is MEDIUM/HIGH (Score ~60-89).
        - Trusted vendors and small amounts are LOW RISK.

        Return strict JSON:
        {{
          "risk_score": <0-100>,
          "analysis": "<short one-sentence explanation>"
        }}
        """
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return JSON only. Do NOT include extra text."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("risk_score", 0), result.get("analysis", "Analysis unavailable")
    except Exception as e:
        print(f"❌ Groq Error (risk): {e}")
        # Default to high risk so the demo still shows something
        return 95, "Payment exceeds $5,000 to an unknown vendor"

# --- GROQ Q&A: Conversational Answers About This Transaction ---

def answer_risk_question_with_groq(question: str):
    """
    Takes the user's spoken question and the last transaction context,
    returns an explanation string to speak back to the caller.
    """
    print(f"🧠 [GROQ Q&A] Question: {question}")
    try:
        context = f"""
        Transaction Details:
        - Action: {LAST_TRANSACTION.get('action')}
        - Payload: {json.dumps(LAST_TRANSACTION.get('payload'))}
        - Reasoning: {LAST_TRANSACTION.get('reasoning')}
        - Risk Score: {CURRENT_STATE.get('risk_score')}
        - Initial Analysis: {CURRENT_STATE.get('analysis')}
        """

        prompt = f"""
        You are Sentinel, a security AI talking to a human approver over the phone.

        Context:
        {context}

        The human asked: "{question}".

        Your job:
        - Answer clearly in 2–4 sentences.
        - Explain the risk in simple terms.
        - Reference the amount, vendor, and why it's unusual.
        - If they seem like they want reassurance, suggest a safe action (like ‘verify vendor first’).
        - DO NOT mention that you're an AI model or JSON.

        Return ONLY the spoken answer, no JSON, no quotes.
        """
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You speak as Sentinel over the phone. No JSON. Just the spoken answer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
        )
        answer = response.choices[0].message.content.strip()
        print(f"🧠 [GROQ Q&A] Answer: {answer}")
        return answer
    except Exception as e:
        print(f"❌ Groq Error (Q&A): {e}")
        return "I'm having trouble accessing my analysis engine right now. From what I see, this still looks like a high-risk payment to an unknown vendor. I would verify the vendor details before approving."

# --- TELNYX HELPERS ---

def telnyx_post(path, payload):
    """Wrapper with logging."""
    url = f"{TELNYX_BASE_URL}{path}"
    try:
        print(f"📡 [TELNYX] POST {url} -> {payload}")
        r = requests.post(url, headers=TELNYX_HEADERS, json=payload)
        print(f"📡 [TELNYX] Response {r.status_code}: {r.text}")
        return r
    except Exception as e:
        print(f"❌ [TELNYX] Error POST {url}: {e}")
        return None

def trigger_voice_auth():
    """
    Start the Telnyx outbound call. We encode a summary into client_state
    so that when the call is answered, we can read it out.
    """
    if not ADMIN_PHONE_NUMBER or not TELNYX_PHONE_NUMBER:
        print("❌ [TELNYX] Missing phone numbers")
        return False

    summary = f"High risk payment detected. Amount {LAST_TRANSACTION['payload'].get('amount')} dollars to {LAST_TRANSACTION['payload'].get('vendor')}."
    encoded_state = base64.b64encode(summary.encode("utf-8")).decode("utf-8")

    print(f"📞 [TELNYX] Dialing {ADMIN_PHONE_NUMBER}...")
    resp = telnyx_post("/calls", {
        "connection_id": TELNYX_CONNECTION_ID,
        "to": ADMIN_PHONE_NUMBER,
        "from": TELNYX_PHONE_NUMBER,
        "stream_track": "inbound_track",
        "client_state": encoded_state
    })

    if resp is None or not resp.ok:
        print("❌ [TELNYX] Failed to start call")
        return False

    return True

def start_dtmf_menu(call_id: str, summary: str):
    """
    When the call is answered, speak the summary and instructions,
    and gather DTMF (1 = approve, 2 = conversational Q&A).
    """
    message = (
        f"{summary} "
        "This payment looks high risk. "
        "Press 1 to approve immediately. "
        "Press 2 if you want to ask me questions about this transaction after the beep."
    )

    telnyx_post(f"/calls/{call_id}/actions/gather_using_speak", {
        "payload": message,
        "language": "en-US",
        "voice": "female",
        "input_type": "dtmf",
        "beep_enabled": True,
        "timeout_millis": 10000  # 10s to press a key
    })

def start_speech_question_gather(call_id: str):
    """
    After the user presses 2, we go into Q&A mode.
    We prompt them and then gather speech.
    """
    prompt = (
        "Okay. You can now ask any question about this transaction after the beep. "
        "For example, you can ask why this is risky, what looks unusual, "
        "or what you should do next."
    )

    telnyx_post(f"/calls/{call_id}/actions/gather_using_speak", {
        "payload": prompt,
        "language": "en-US",
        "voice": "female",
        "input_type": "speech",
        "beep_enabled": True,
        "timeout_millis": 15000  # 15 seconds to speak
    })

def speak_and_loop_question(call_id: str, answer: str):
    """
    Speak the answer and then invite another question.
    """
    message = (
        f"{answer} "
        "If you have another question, ask it after the beep. "
        "Otherwise, you can say goodbye to end the call."
    )

    telnyx_post(f"/calls/{call_id}/actions/gather_using_speak", {
        "payload": message,
        "language": "en-US",
        "voice": "female",
        "input_type": "speech",
        "beep_enabled": True,
        "timeout_millis": 15000
    })

# --- API ENDPOINTS ---

@app.get("/api/sentinel/status")
def get_status():
    """Frontend polls this to see what the Agent is doing"""
    return CURRENT_STATE

@app.post("/api/sentinel/execute")
def execute_action(request: ActionRequest):
    global CURRENT_STATE, LAST_TRANSACTION

    # Store context for later Q&A
    LAST_TRANSACTION["action"] = request.action
    LAST_TRANSACTION["payload"] = request.payload
    LAST_TRANSACTION["reasoning"] = request.reasoning

    CURRENT_STATE["status"] = "ANALYZING"

    with sentry_sdk.start_transaction(op="agent.action", name=f"Execute {request.action}") as span:
        span.set_data("payload", request.payload)

        risk_score, analysis = analyze_risk_with_groq(request.action, request.payload, request.reasoning)
        CURRENT_STATE["risk_score"] = risk_score
        CURRENT_STATE["analysis"] = analysis
        span.set_data("risk_score", risk_score)

        print(f"🔎 [RISK] Score={risk_score}, Analysis={analysis}")

        if risk_score > 50:
            sentry_sdk.set_tag("risk", "HIGH")
            CURRENT_STATE["status"] = "BLOCKED_AWAITING_AUTH"

            ok = trigger_voice_auth()
            if not ok:
                return {
                    "status": "ERROR_TELNYX",
                    "risk_score": risk_score,
                    "analysis": analysis
                }

            return {
                "status": "BLOCKED_AWAITING_AUTH",
                "risk_score": risk_score,
                "analysis": analysis
            }

        sentry_sdk.set_tag("risk", "LOW")
        CURRENT_STATE["status"] = "APPROVED"
        return {"status": "EXECUTED", "risk_score": risk_score, "analysis": analysis}

# --- TELNYX WEBHOOK ---

@app.post("/api/telnyx/webhook")
async def telnyx_webhook(request: Request):
    """
    Handles Telnyx call events:
    - call.answered: Play summary + menu (1 approve, 2 Q&A).
    - call.dtmf.received: 1 = approve, 2 = enter Q&A mode.
    - call.gather.ended: Handle spoken question, answer with Groq, loop.
    """
    global CURRENT_STATE

    data = await request.json()
    event_type = data.get("data", {}).get("event_type")
    payload = data.get("data", {}).get("payload", {}) or {}
    call_id = payload.get("call_control_id")

    print(f"⚡ [WEBHOOK] Event: {event_type}")

    if not call_id:
        print("⚠️ [WEBHOOK] No call_id in payload")
        return {"status": "ok"}

    # --- 1) CALL ANSWERED: Speak risk summary + DTMF menu ---
    if event_type == "call.answered":
        client_state = payload.get("client_state")
        summary = "Authorization required for a high-risk payment."

        if client_state:
            try:
                summary = base64.b64decode(client_state).decode("utf-8")
            except Exception as e:
                print(f"⚠️ [WEBHOOK] Failed to decode client_state: {e}")

        print(f"📞 [CALL] Answered. Summary for user: {summary}")
        start_dtmf_menu(call_id, summary)

    # --- 2) DTMF RECEIVED: 1 = approve, 2 = Q&A mode ---
    elif event_type == "call.dtmf.received":
        digit = payload.get("digit")
        CURRENT_STATE["last_digit"] = digit
        print(f"🔢 [DTMF] Digit pressed: {digit}")

        # APPROVE
        if digit == "1":
            print("✅ [AUTH] Approved via DTMF 1")
            CURRENT_STATE["status"] = "APPROVED"

            telnyx_post(f"/calls/{call_id}/actions/speak", {
                "payload": "Approval confirmed. The transaction will proceed. Goodbye.",
                "language": "en-US",
                "voice": "female"
            })

            # Optionally hang up after speaking (Telnyx will usually end after message)
            telnyx_post(f"/calls/{call_id}/actions/hangup", {})

        # ENTER Q&A MODE
        elif digit == "2":
            print("🗣️ [Q&A] Entering conversational mode")
            CURRENT_STATE["status"] = "QNA_MODE"

            start_speech_question_gather(call_id)

        else:
            # Unknown key - repeat menu
            print("❓ [DTMF] Unknown key, repeating menu")
            summary = CURRENT_STATE.get("analysis", "High-risk payment detected.")
            start_dtmf_menu(call_id, summary)

    # --- 3) GATHER ENDED: Handle spoken questions in Q&A mode ---
    elif event_type == "call.gather.ended":
        # Depending on your Telnyx config, the transcription field might look like this:
        # payload["speech"]["transcription"]
        # or payload["transcription"]
        speech = payload.get("speech") or {}
        question_text = None

        if isinstance(speech, dict):
            question_text = speech.get("transcription") or speech.get("text")

        if not question_text:
            question_text = payload.get("transcription")

        if not question_text:
            print("⚠️ [Q&A] No transcription found in gather payload")
            telnyx_post(f"/calls/{call_id}/actions/speak", {
                "payload": "I didn't catch that. Please ask your question again after the beep.",
                "language": "en-US",
                "voice": "female"
            })
            start_speech_question_gather(call_id)
            return {"status": "ok"}

        question_text = question_text.strip()
        print(f"🗣️ [Q&A] User asked: {question_text}")
        CURRENT_STATE["last_question"] = question_text

        # If user wants to end the conversation
        lower_q = question_text.lower()
        if "goodbye" in lower_q or "that's all" in lower_q or "no more" in lower_q:
            print("👋 [Q&A] User ended conversation by voice")
            telnyx_post(f"/calls/{call_id}/actions/speak", {
                "payload": "Got it. Ending the call now. Goodbye.",
                "language": "en-US",
                "voice": "female"
            })
            telnyx_post(f"/calls/{call_id}/actions/hangup", {})
            return {"status": "ok"}

        # Use Groq to answer the question about this transaction
        answer = answer_risk_question_with_groq(question_text)
        CURRENT_STATE["last_answer"] = answer

        # Speak answer and loop
        speak_and_loop_question(call_id, answer)

    else:
        # Just log other events so you can see them in the console
        print(f"ℹ️ [WEBHOOK] Unhandled event type: {event_type}")

    return {"status": "ok"}
