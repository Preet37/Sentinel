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
TELNYX_CONNECTION_ID = "2834931739384612416" 
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
    "analysis": "System Ready"
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
            messages=[{"role": "system", "content": "Return JSON only."}, {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("risk_score", 0), result.get("analysis", "Analysis")
    except Exception as e:
        print(f"❌ Groq Error: {e}")
        return 95, "AI Offline - Defaulting to High Risk"

def trigger_voice_auth(action, details, risk_score):
    print(f"📞 [TELNYX] Dialing {ADMIN_PHONE_NUMBER}...")
    message = f"Vault Keeper Alert. Risk Score {risk_score}. Requesting {action}. Press 1 to approve."
    encoded_state = base64.b64encode(message.encode("utf-8")).decode("utf-8")
    
    try:
        requests.post(f"{TELNYX_BASE_URL}/calls", json={
            "connection_id": TELNYX_CONNECTION_ID,
            "to": ADMIN_PHONE_NUMBER,
            "from": TELNYX_PHONE_NUMBER,
            "stream_track": "inbound_track",
            "client_state": encoded_state
        }, headers=TELNYX_HEADERS)
        return True
    except:
        return False

# --- API ENDPOINTS ---

@app.get("/api/sentinel/status")
def get_status():
    """Frontend polls this to see what the Agent is doing"""
    return CURRENT_STATE

@app.post("/api/sentinel/execute")
def execute_action(request: ActionRequest):
    global CURRENT_STATE
    # Update State: Agent is trying something!
    CURRENT_STATE["status"] = "ANALYZING"
    
    with sentry_sdk.start_transaction(op="agent.action", name=f"Execute {request.action}") as span:
        span.set_data("payload", request.payload)
        
        risk_score, analysis = analyze_risk_with_groq(request.action, request.payload, request.reasoning)
        
        # Update Global State with AI Results
        CURRENT_STATE["risk_score"] = risk_score
        CURRENT_STATE["analysis"] = analysis
        
        span.set_data("risk_score", risk_score)

        if risk_score > 50:
            sentry_sdk.set_tag("risk", "HIGH")
            CURRENT_STATE["status"] = "BLOCKED_AWAITING_AUTH" # <--- FRONTEND WILL SEE THIS
            
            trigger_voice_auth(request.action, str(request.payload), risk_score)
            
            return {
                "status": "BLOCKED_AWAITING_AUTH", 
                "risk_score": risk_score,
                "analysis": analysis
            }

        CURRENT_STATE["status"] = "APPROVED"
        sentry_sdk.set_tag("risk", "LOW")
        return {"status": "EXECUTED", "risk_score": risk_score}

@app.post("/api/telnyx/webhook")
async def telnyx_webhook(request: Request):
    global CURRENT_STATE
    data = await request.json()
    event_type = data.get("data", {}).get("event_type")
    call_id = data.get("data", {}).get("payload", {}).get("call_control_id")
    payload = data.get("data", {}).get("payload", {})

    print(f"⚡ [WEBHOOK] Event: {event_type}")

    if event_type == "call.answered":
        client_state = payload.get("client_state")
        msg = "Authorization required."
        if client_state:
            try: msg = base64.b64decode(client_state).decode("utf-8")
            except: pass
            
        requests.post(f"{TELNYX_BASE_URL}/calls/{call_id}/actions/gather_using_speak", headers=TELNYX_HEADERS, json={
            "payload": msg, "language": "en-US", "voice": "male", "input_type": "dtmf", "timeout_millis": 60000
        })

    elif event_type == "call.dtmf.received":
        digit = payload.get("digit")
        print(f"🔢 BUTTON PRESSED: {digit}")
        
        if digit == "1":
            print("✅ AUTHENTICATION VERIFIED!")
            CURRENT_STATE["status"] = "APPROVED"  # <--- UPDATES FRONTEND TO GREEN
            requests.post(f"{TELNYX_BASE_URL}/calls/{call_id}/actions/speak", headers=TELNYX_HEADERS, json={
                "payload": "Access Granted. Goodbye."
            })
            # Reset after 10 seconds so the dashboard goes back to idle eventually
            # (Optional logic, handled by frontend usually)

    return {"status": "ok"}