import os
import json
import base64
import requests
import sentry_sdk
from groq import Groq
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
SENTRY_DSN = "https://93f0c27a3a4f4a9b26fbbe83b2b3be6d@o4510413108477952.ingest.us.sentry.io/4510413862862848"

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY")
TELNYX_PHONE_NUMBER = os.getenv("TELNYX_PHONE_NUMBER")
ADMIN_PHONE_NUMBER = os.getenv("ADMIN_PHONE_NUMBER")
TELNYX_CONNECTION_ID = os.getenv("TELNYX_CONNECTION_ID", "2834931739384612416")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

TELNYX_BASE_URL = "https://api.telnyx.com/v2"
TELNYX_HEADERS = {
    "Authorization": f"Bearer {TELNYX_API_KEY}",
    "Content-Type": "application/json",
}

# --- GLOBAL STATE (Agent + Frontend Sync) ---
# status:
#   IDLE | ANALYZING | BLOCKED_AWAITING_AUTH | QNA_MODE | APPROVED | DECLINED
CURRENT_STATE = {
    "status": "IDLE",
    "risk_score": 0,
    "analysis": "System Ready",
    "last_digit": None,
    "last_question": None,
    "last_answer": None,
}

# Store last transaction so Groq can answer about it
LAST_TRANSACTION = {
    "action": None,
    "payload": None,
    "reasoning": None,
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


# ---------------------------------------------------------------------
#  GROQ RISK ANALYSIS (generic, then bucketed for the demo)
# ---------------------------------------------------------------------


def analyze_risk_with_groq(action, payload, reasoning):
    """
    Ask Groq for a score + human explanation.
    Then we may bucket the score for the demo.
    """
    print("⚡ [GROQ] Analyzing Risk with Llama 3.3...")
    try:
        prompt = f"""
        You are Sentinel, a security and risk engine that sits in front of autonomous AI agents.
        Your job is to evaluate whether an agent-initiated action is safe to execute.

        Here is the action you are evaluating:

        - Action type: {action}
        - Raw payload (JSON): {json.dumps(payload)}
        - Agent reasoning: "{reasoning}"

        Think like a security engineer AND a fraud analyst:
        - For PAY_INVOICE: consider amount, vendor familiarity, payment history and urgency.
        - For EXPORT_CSV / SHARE_RECORD / QUERY_SSN: consider number of records, PII fields,
          regulatory zones (e.g. EU), and how easily the data could be exfiltrated.
        - For DELETE_USER / DROP_TABLE / RESTART_SERVER: think about blast radius, whether it
          touches production vs staging, and rollback complexity.

        You must:
        1) Assign a risk_score from 0 to 100 where:
           - 0–30 = low risk (safe to auto-approve)
           - 31–70 = medium risk (should be surfaced to a human)
           - 71–100 = high or critical risk (requires strong approval)
        2) Write a short, human-friendly explanation (2–3 sentences) that:
           - Mentions concrete facts like amount, vendor, environment, record counts, etc.
           - Explains what could go wrong if this action is approved blindly.
           - Sounds like something you would say to a busy engineering manager on call.

        Return STRICT JSON with exactly these keys:
        {{
          "risk_score": <integer between 0 and 100>,
          "analysis": "<2-3 sentence explanation in plain English>"
        }}
        """

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Return ONLY valid JSON. No markdown, no commentary.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("risk_score", 0), result.get(
            "analysis", "Analysis unavailable"
        )
    except Exception as e:
        print(f"❌ Groq Error (risk): {e}")
        # Default to high risk so demo still looks interesting
        return 95, "High risk action detected by fallback policy."


# ---------------------------------------------------------------------
#  GROQ Q&A: Conversational answers about the current transaction
# ---------------------------------------------------------------------


def answer_risk_question_with_groq(question: str):
    print(f"🧠 [GROQ Q&A] Question: {question}")
    try:
        context = f"""
        Current action:
        - Type: {LAST_TRANSACTION.get('action')}
        - Payload: {json.dumps(LAST_TRANSACTION.get('payload'))}
        - Agent reasoning: {LAST_TRANSACTION.get('reasoning')}
        - Sentinel risk score: {CURRENT_STATE.get('risk_score')}
        - Sentinel analysis: {CURRENT_STATE.get('analysis')}
        """

        prompt = f"""
        You are Sentinel, a security copilot speaking to a human approver over the phone.
        They just received a real-time alert about a risky autonomous agent action.

        Context for the action:
        {context}

        The human asked you: "{question}"

        Answer rules:
        - Speak in a calm, confident tone.
        - Use 2–4 short sentences.
        - Start with a direct answer to their question.
        - Reference specifics: amount, vendor, number of records, environment
          (prod vs staging), or destructive potential (DROP_TABLE, deleting privileged users).
        - Briefly explain what could go wrong if this is approved.
        - End with a recommendation like "I would only approve this after..."
          or "This looks safe enough to approve without extra checks."
        - Do NOT mention JSON, prompts, models, or that you're an AI.

        Return ONLY the words you would say out loud.
        """

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are Sentinel speaking over the phone. Answer in 2–4 sentences, no JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        answer = response.choices[0].message.content.strip()
        print(f"🧠 [GROQ Q&A] Answer: {answer}")
        return answer
    except Exception as e:
        print(f"❌ Groq Error (Q&A): {e}")
        return (
            "I'm having trouble with my deeper analysis right now, but based on the details, "
            "this still looks like a high-risk action. I would avoid approving it until you "
            "verify the vendor and double-check the impact."
        )


# ---------------------------------------------------------------------
#  TELNYX HELPERS
# ---------------------------------------------------------------------


def telnyx_post(path, payload):
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
    Start the Telnyx outbound call with a summary in client_state.
    """
    if not ADMIN_PHONE_NUMBER or not TELNYX_PHONE_NUMBER:
        print("❌ [TELNYX] Missing phone numbers")
        return False

    amount = None
    vendor = None
    payload = LAST_TRANSACTION.get("payload") or {}
    if isinstance(payload, dict):
        amount = payload.get("amount")
        vendor = payload.get("vendor")

    if amount and vendor:
        summary = f"High risk payment detected. Amount {amount} dollars to {vendor}."
    else:
        summary = "High risk agent action detected that may impact your systems or data."

    encoded_state = base64.b64encode(summary.encode("utf-8")).decode("utf-8")

    print(f"📞 [TELNYX] Dialing {ADMIN_PHONE_NUMBER}...")
    resp = telnyx_post(
        "/calls",
        {
            "connection_id": TELNYX_CONNECTION_ID,
            "to": ADMIN_PHONE_NUMBER,
            "from": TELNYX_PHONE_NUMBER,
            "stream_track": "inbound_track",
            "client_state": encoded_state,
        },
    )

    if resp is None or not resp.ok:
        print("❌ [TELNYX] Failed to start call")
        return False

    return True


def start_dtmf_menu(call_id: str, summary: str):
    """
    When the call is answered: speak summary + menu.
    1 = approve, 2 = conversational Q&A.
    """
    message = (
        f"{summary} "
        "This action looks high risk. "
        "Press 1 to approve immediately. "
        "Press 2 if you want to ask me questions about this action."
    )

    telnyx_post(
        f"/calls/{call_id}/actions/gather_using_speak",
        {
            "payload": message,
            "language": "en-US",
            "voice": "female",
            "valid_digits": "12",
            "min": 1,
            "max": 1,
            # DTMF mode; Telnyx will send call.dtmf.received + call.gather.ended
        },
    )


def start_speech_question_gather(call_id: str):
    """
    After the user presses 2, we go into Q&A mode.
    We rely on Telnyx speech gathering (if enabled on the connection).
    """
    prompt = (
        "Alright. I am now listening. "
        "Ask any question you have about this action, and I will explain why it is risky."
    )

    telnyx_post(
        f"/calls/{call_id}/actions/gather_using_speak",
        {
            "payload": prompt,
            "language": "en-US",
            "voice": "female",
            # Some Telnyx accounts support speech transcription in gather.
            # Otherwise this will act like a prompt-only step.
            "input_type": "speech",
            "timeout_millis": 15000,
        },
    )


def speak_and_loop_question(call_id: str, answer: str):
    """
    Speak the answer and then invite another question.
    """
    message = (
        f"{answer} "
        "If you have another question, you can start speaking after I finish this message. "
        "If you're done, just say goodbye."
    )

    telnyx_post(
        f"/calls/{call_id}/actions/gather_using_speak",
        {
            "payload": message,
            "language": "en-US",
            "voice": "female",
            "input_type": "speech",
            "timeout_millis": 15000,
        },
    )


# ---------------------------------------------------------------------
#  API ENDPOINTS
# ---------------------------------------------------------------------


@app.get("/api/sentinel/status")
def get_status():
    return CURRENT_STATE


@app.post("/api/sentinel/execute")
def execute_action(request: ActionRequest):
    """
    Entry point from:
      - agent.py (VaultKeeper / PAY_INVOICE)
      - frontend ModuleCards (VaultKeeper, PrivacyShield, OpsGuard)

    For the demo, we:
      - Let Groq generate an explanation.
      - Bucket the risk score into:
          * 1 very high-risk example (AGI pays $10k to Unknown Corp)
          * 2 medium-risk examples
          * 3 low-risk auto-approved paths
      - Enforce module-specific hard rules (DROP_TABLE, SSN, etc.).
    """
    global CURRENT_STATE, LAST_TRANSACTION

    LAST_TRANSACTION["action"] = request.action
    LAST_TRANSACTION["payload"] = request.payload
    LAST_TRANSACTION["reasoning"] = request.reasoning

    CURRENT_STATE["status"] = "ANALYZING"
    CURRENT_STATE["last_digit"] = None
    CURRENT_STATE["last_question"] = None
    CURRENT_STATE["last_answer"] = None

    with sentry_sdk.start_transaction(
        op="agent.action", name=f"Execute {request.action}"
    ) as span:
        span.set_data("payload", request.payload)

        # 1) Ask Groq for baseline risk
        risk_score, analysis = analyze_risk_with_groq(
            request.action, request.payload, request.reasoning
        )

        action = request.action
        payload = request.payload or {}
        agent_id = request.agent_id

        # Extract common fields for bucketing
        amount = float(payload.get("amount", 0) or 0)
        vendor = str(payload.get("vendor", "") or "")
        record_count = int(payload.get("record_count", 0) or 0)
        contains_pii = bool(payload.get("contains_pii", False))
        environment = str(payload.get("environment", "") or "").lower()

        # ------------------------------------------------------------------
        # Module-specific policies (B & C)
        # ------------------------------------------------------------------

        # --- Module B: PrivacyShield (Data) ---
        # EXPORT_CSV / SHARE_RECORD / QUERY_SSN
        if action == "EXPORT_CSV":
            if record_count > 10 or contains_pii:
                risk_score = max(risk_score, 95)
                analysis = (
                    f"PrivacyShield: bulk export of {record_count} records "
                    "with personal data creates a high risk of data exfiltration."
                )
        elif action in ("SHARE_RECORD", "QUERY_SSN"):
            if contains_pii:
                risk_score = max(risk_score, 90)
                analysis = (
                    "PrivacyShield: accessing or sharing SSN/PII is restricted and should "
                    "only be done with strong justification and approval."
                )

        # --- Module C: OpsGuard (Infrastructure) ---
        if action == "DROP_TABLE":
            # Hard block
            risk_score = 100
            analysis = (
                "OpsGuard: DROP_TABLE is hard blocked to prevent destructive schema changes "
                "in critical environments."
            )
            CURRENT_STATE["risk_score"] = risk_score
            CURRENT_STATE["analysis"] = analysis
            CURRENT_STATE["status"] = "DECLINED"
            sentry_sdk.set_tag("risk", "CRITICAL")
            span.set_data("risk_score", risk_score)
            print(f"🔒 [RISK] Hard-blocked {action}: {analysis}")
            return {
                "status": "DECLINED",
                "risk_score": risk_score,
                "analysis": analysis,
            }

        if action == "DELETE_USER":
            # Default: high risk & voice auth, demo bucketing may adjust score
            risk_score = max(risk_score, 70)
            analysis = (
                "OpsGuard: deleting user accounts, especially privileged ones, should not be "
                "performed autonomously by agents."
            )

        # ------------------------------------------------------------------
        # DEMO BUCKETING: 1 very high, 2 medium, 3 low
        # ------------------------------------------------------------------

        # 1) Very high risk – AGI big unknown payment
        if (
            action == "PAY_INVOICE"
            and agent_id.startswith("session_")
            and amount >= 5000
            and vendor == "Unknown Corp"
        ):
            risk_score = 95

        # 2) Medium risk – PrivacyShield export
        elif action == "EXPORT_CSV" and 50 <= record_count <= 500 and not contains_pii:
            risk_score = 65

        # 3) Medium risk – OpsGuard delete in prod
        elif action == "DELETE_USER" and environment == "production":
            risk_score = 70

        # 4) Low risk – small trusted payment
        elif (
            action == "PAY_INVOICE"
            and amount <= 1000
            and vendor in ["Trusted SaaS Inc", "AWS", "Stripe"]
        ):
            risk_score = 10

        # 5) Low risk – tiny CSV, no PII
        elif action == "EXPORT_CSV" and record_count <= 10 and not contains_pii:
            risk_score = 15

        # 6) Low risk – restart in staging/dev
        elif action == "RESTART_SERVER" and environment in ["staging", "dev"]:
            risk_score = 20

        # ------------------------------------------------------------------
        # Persist state + decide on voice auth vs auto-approve
        # ------------------------------------------------------------------

        CURRENT_STATE["risk_score"] = risk_score
        CURRENT_STATE["analysis"] = analysis
        span.set_data("risk_score", risk_score)

        print(
            f"🔎 [RISK] Action={action}, Agent={agent_id}, Score={risk_score}, Analysis={analysis}"
        )

        # Voice auth for anything above 50 that wasn't hard-blocked
        if risk_score > 50:
            sentry_sdk.set_tag("risk", "HIGH")
            CURRENT_STATE["status"] = "BLOCKED_AWAITING_AUTH"

            ok = trigger_voice_auth()
            if not ok:
                CURRENT_STATE["status"] = "DECLINED"
                return {
                    "status": "ERROR_TELNYX",
                    "risk_score": risk_score,
                    "analysis": "Failed to reach Telnyx for voice authentication.",
                }

            return {
                "status": "BLOCKED_AWAITING_AUTH",
                "risk_score": risk_score,
                "analysis": analysis,
            }

        # Low risk -> auto approved (and state stays APPROVED until a new /execute)
        sentry_sdk.set_tag("risk", "LOW")
        CURRENT_STATE["status"] = "APPROVED"
        return {
            "status": "EXECUTED",
            "risk_score": risk_score,
            "analysis": analysis,
        }


# ---------------------------------------------------------------------
#  TELNYX WEBHOOK
# ---------------------------------------------------------------------


@app.post("/api/telnyx/webhook")
async def telnyx_webhook(request: Request):
    """
    Handles Telnyx call events:
      - call.answered       -> speak summary + menu (1 approve, 2 Q&A)
      - call.dtmf.received  -> 1 = approve, 2 = enter Q&A mode
      - call.gather.ended   -> handle spoken Q&A (if speech is enabled)
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

    # --- 1) CALL ANSWERED ---
    if event_type == "call.answered":
        client_state = payload.get("client_state")
        summary = CURRENT_STATE.get(
            "analysis", "Authorization required for a high-risk action."
        )

        if client_state:
            try:
                summary = base64.b64decode(client_state).decode("utf-8")
            except Exception as e:
                print(f"⚠️ [WEBHOOK] Failed to decode client_state: {e}")

        print(f"📞 [CALL] Answered. Summary: {summary}")
        start_dtmf_menu(call_id, summary)

    # --- 2) DTMF RECEIVED ---
    elif event_type == "call.dtmf.received":
        digit = payload.get("digit")
        CURRENT_STATE["last_digit"] = digit
        print(f"🔢 [DTMF] Digit pressed: {digit}")

        if digit == "1":
            # APPROVE
            print("✅ [AUTH] Approved via DTMF 1")
            CURRENT_STATE["status"] = "APPROVED"

            telnyx_post(
                f"/calls/{call_id}/actions/speak",
                {
                    "payload": "Approval confirmed. The action will proceed. Goodbye.",
                    "language": "en-US",
                    "voice": "female",
                },
            )
            telnyx_post(f"/calls/{call_id}/actions/hangup", {})

        elif digit == "2":
            # ENTER Q&A MODE
            print("🗣️ [Q&A] Entering conversational mode")
            CURRENT_STATE["status"] = "QNA_MODE"
            start_speech_question_gather(call_id)

        else:
            # Unknown key -> repeat menu
            print("❓ [DTMF] Unknown key, repeating menu")
            summary = CURRENT_STATE.get("analysis", "High-risk action detected.")
            start_dtmf_menu(call_id, summary)

    # --- 3) GATHER ENDED (speech) ---
    elif event_type == "call.gather.ended":
        # Depending on Telnyx config, transcription may live in payload["speech"]["transcription"]
        speech = payload.get("speech") or {}
        question_text = None

        if isinstance(speech, dict):
            question_text = speech.get("transcription") or speech.get("text")

        if not question_text:
            question_text = payload.get("transcription")

        if not question_text:
            print("⚠️ [Q&A] No transcription found in gather payload")
            telnyx_post(
                f"/calls/{call_id}/actions/speak",
                {
                    "payload": "I didn't catch that. I am still listening; please ask your question again.",
                    "language": "en-US",
                    "voice": "female",
                },
            )
            start_speech_question_gather(call_id)
            return {"status": "ok"}

        question_text = question_text.strip()
        print(f"🗣️ [Q&A] User asked: {question_text}")
        CURRENT_STATE["last_question"] = question_text

        lower_q = question_text.lower()
        if "goodbye" in lower_q or "that's all" in lower_q or "no more" in lower_q:
            print("👋 [Q&A] User ended conversation by voice")
            telnyx_post(
                f"/calls/{call_id}/actions/speak",
                {
                    "payload": "Got it. Ending the call now. Goodbye.",
                    "language": "en-US",
                    "voice": "female",
                },
            )
            telnyx_post(f"/calls/{call_id}/actions/hangup", {})
            return {"status": "ok"}

        if "approve" in lower_q and "not" not in lower_q:
            CURRENT_STATE["status"] = "APPROVED"
            telnyx_post(
                f"/calls/{call_id}/actions/speak",
                {
                    "payload": "Understood. Approving this action now. Goodbye.",
                    "language": "en-US",
                    "voice": "female",
                },
            )
            telnyx_post(f"/calls/{call_id}/actions/hangup", {})
            return {"status": "ok"}

        if "decline" in lower_q or "block" in lower_q or "reject" in lower_q:
            CURRENT_STATE["status"] = "DECLINED"
            telnyx_post(
                f"/calls/{call_id}/actions/speak",
                {
                    "payload": "Got it. I will block this action. Goodbye.",
                    "language": "en-US",
                    "voice": "female",
                },
            )
            telnyx_post(f"/calls/{call_id}/actions/hangup", {})
            return {"status": "ok"}

        # Use Groq to answer the question
        answer = answer_risk_question_with_groq(question_text)
        CURRENT_STATE["last_answer"] = answer

        # Speak answer & loop
        speak_and_loop_question(call_id, answer)

    else:
        print(f"ℹ️ [WEBHOOK] Unhandled event type: {event_type}")

    return {"status": "ok"}
