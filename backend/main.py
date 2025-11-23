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
TELNYX_PHONE_NUMBER = os.getenv("TELNYX_PHONE_NUMBER")  # your Telnyx number, e.g. +15616680789
ADMIN_PHONE_NUMBER = os.getenv("ADMIN_PHONE_NUMBER")    # your cell, e.g. +16507890786
TELNYX_CONNECTION_ID = os.getenv("TELNYX_CONNECTION_ID") or "2834931739384612416"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

TELNYX_BASE_URL = "https://api.telnyx.com/v2"
TELNYX_HEADERS = {
    "Authorization": f"Bearer {TELNYX_API_KEY}",
    "Content-Type": "application/json"
}

# --- GLOBAL STATE (To Sync Agent & Frontend) ---
CURRENT_STATE = {
    "status": "IDLE",
    "risk_score": 0,
    "analysis": "System Ready",
    "last_action": None,
    "last_payload": None,
    "last_digit": None,
}

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        send_default_pii=True,
        debug=False,  # set True if you want the crazy logs again
    )

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


# --- HELPER: AI RISK ANALYSIS ---
def analyze_risk_with_groq(action, payload, reasoning):
    print("⚡ [GROQ] Analyzing Risk with Llama 3.3...")
    try:
        prompt = f"""
        You are a Financial Security AI. Analyze this transaction request.
        Context: Action: {action}, Details: {json.dumps(payload)}, Reasoning: "{reasoning}"
        Rules:
        - Payment > $5,000 to "Unknown" vendors is CRITICAL RISK (Score 90-100).
        - Return JSON: {{ "risk_score": <0-100>, "analysis": "<short_reason>" }}
        """

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        return result.get("risk_score", 0), result.get("analysis", "Analysis unavailable")
    except Exception as e:
        print(f"❌ Groq Error: {e}")
        # Default to high risk if AI is offline
        return 95, "AI Offline - Defaulting to High Risk"


# --- HELPER: TRIGGER VOICE AUTH ---
def trigger_voice_auth(action: str, payload: dict, risk_score: int):
    """
    Start a Telnyx call to the admin. The detailed prompt will be spoken
    in the webhook when the call is answered.
    """
    print(f"📞 [TELNYX] Dialing {ADMIN_PHONE_NUMBER}...")

    # We still put something in client_state, but webhook will build the main prompt
    summary = {
        "action": action,
        "risk_score": risk_score,
        "amount": payload.get("amount"),
        "vendor": payload.get("vendor"),
    }
    encoded_state = base64.b64encode(json.dumps(summary).encode("utf-8")).decode("utf-8")

    try:
        resp = requests.post(
            f"{TELNYX_BASE_URL}/calls",
            json={
                "connection_id": TELNYX_CONNECTION_ID,
                "to": ADMIN_PHONE_NUMBER,
                "from": TELNYX_PHONE_NUMBER,
                "stream_track": "inbound_track",
                "client_state": encoded_state,
            },
            headers=TELNYX_HEADERS,
        )
        print(f"📡 [TELNYX] /calls response: {resp.status_code} {resp.text}")
        return resp.ok
    except Exception as e:
        print(f"❌ [TELNYX] Error starting call: {e}")
        return False


# --- API ENDPOINTS ---

@app.get("/api/sentinel/status")
def get_status():
    """Frontend & agent poll this to see what the Sentinel is doing."""
    return CURRENT_STATE


@app.post("/api/sentinel/execute")
def execute_action(request: ActionRequest):
    global CURRENT_STATE

    CURRENT_STATE["status"] = "ANALYZING"

    with sentry_sdk.start_transaction(
        op="agent.action", name=f"Execute {request.action}"
    ) as span:
        span.set_data("payload", request.payload)

        risk_score, analysis = analyze_risk_with_groq(
            request.action, request.payload, request.reasoning
        )

        # Update global state with AI results
        CURRENT_STATE["risk_score"] = risk_score
        CURRENT_STATE["analysis"] = analysis
        CURRENT_STATE["last_action"] = request.action
        CURRENT_STATE["last_payload"] = request.payload

        span.set_data("risk_score", risk_score)

        # High risk → require voice auth
        if risk_score > 50:
            sentry_sdk.set_tag("risk", "HIGH")
            CURRENT_STATE["status"] = "BLOCKED_AWAITING_AUTH"

            trigger_voice_auth(request.action, request.payload, risk_score)

            return {
                "status": "BLOCKED_AWAITING_AUTH",
                "risk_score": risk_score,
                "analysis": analysis,
            }

        # Low risk → auto-execute
        sentry_sdk.set_tag("risk", "LOW")
        CURRENT_STATE["status"] = "APPROVED"
        return {"status": "EXECUTED", "risk_score": risk_score}


@app.post("/api/telnyx/webhook")
async def telnyx_webhook(request: Request):
    """
    Handles Telnyx call events:
    - call.answered        → speak summary + ask for 1 (approve) or 2 (details)
    - call.dtmf.received   → 1 = approve, 2 = speak details + re-prompt
    """
    global CURRENT_STATE

    data = await request.json()
    event_type = data.get("data", {}).get("event_type")
    payload = data.get("data", {}).get("payload", {}) or {}
    call_id = payload.get("call_control_id")

    print(f"⚡ [WEBHOOK] Event: {event_type}")

    # Helper: get transaction info from global state
    last_payload = CURRENT_STATE.get("last_payload") or {}
    amount = last_payload.get("amount", "an unknown amount")
    vendor = last_payload.get("vendor", "an unknown vendor")
    risk_score = CURRENT_STATE.get("risk_score", 0)
    analysis = CURRENT_STATE.get("analysis", "")

    if event_type == "call.answered":
        # When you pick up, explain the situation & ask for 1 or 2
        message = (
            f"Vault Keeper Alert. We detected a high risk transaction. "
            f"Risk score {risk_score} out of 100. "
            f"The agent is requesting a payment of {amount} dollars to vendor {vendor}. "
            "If you approve this transaction, press 1. "
            "If you want more details before deciding, press 2."
        )

        requests.post(
            f"{TELNYX_BASE_URL}/calls/{call_id}/actions/gather_using_speak",
            headers=TELNYX_HEADERS,
            json={
                "payload": message,
                "language": "en-US",
                "voice": "male",
                "input_type": "dtmf",
                "timeout_millis": 60000,
            },
        )

    elif event_type == "call.dtmf.received":
        digit = payload.get("digit")
        CURRENT_STATE["last_digit"] = digit
        print(f"🔢 BUTTON PRESSED: {digit}")

        if digit == "1":
            # APPROVE
            print("✅ AUTHENTICATION VERIFIED (1 pressed)!")
            CURRENT_STATE["status"] = "APPROVED"

            requests.post(
                f"{TELNYX_BASE_URL}/calls/{call_id}/actions/speak",
                headers=TELNYX_HEADERS,
                json={
                    "payload": "Access granted. The transaction has been approved. Goodbye.",
                    "language": "en-US",
                    "voice": "male",
                },
            )

        elif digit == "2":
            # MORE DETAILS → speak why it's risky, then re-prompt
            detail_message = (
                f"Here are the details. "
                f"The risk score is {risk_score} out of 100. "
                f"The agent wants to pay {amount} dollars to vendor {vendor}. "
                f"Reason: {analysis}. "
                "If you approve this transaction, press 1. "
                "If you want to hear these details again, press 2."
            )

            requests.post(
                f"{TELNYX_BASE_URL}/calls/{call_id}/actions/gather_using_speak",
                headers=TELNYX_HEADERS,
                json={
                    "payload": detail_message,
                    "language": "en-US",
                    "voice": "male",
                    "input_type": "dtmf",
                    "timeout_millis": 60000,
                },
            )

        else:
            # Unknown key → tell user and re-prompt
            error_msg = (
                "Sorry, I did not understand that input. "
                "Press 1 to approve the transaction, or 2 to hear more details."
            )
            requests.post(
                f"{TELNYX_BASE_URL}/calls/{call_id}/actions/gather_using_speak",
                headers=TELNYX_HEADERS,
                json={
                    "payload": error_msg,
                    "language": "en-US",
                    "voice": "male",
                    "input_type": "dtmf",
                    "timeout_millis": 60000,
                },
            )

    # Always return OK so Telnyx is happy
    return {"status": "ok"}
