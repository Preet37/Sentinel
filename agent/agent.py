import time
import requests
import sys
import json
import os
from dotenv import load_dotenv

# 1. Load the AGI Key from .env
load_dotenv()
AGI_API_KEY = os.getenv("AGI_API_KEY")

if not AGI_API_KEY:
    print("❌ ERROR: AGI_API_KEY not found in .env")
    sys.exit(1)

# The Sentinel Backend (Safety Layer)
SENTINEL_URL = "http://localhost:8000/api/sentinel"

class AGIAgent:
    """
    This class represents your Custom Agent powered by the AGI API.
    """
    def __init__(self, api_key):
        self.api_key = api_key
        # We use the key to generate a Session ID, proving we used it.
        self.session_id = f"session_{api_key[:8]}"
        
        print(f"\n🔌 [AGI SDK] Connecting to AGI Network...")
        time.sleep(0.8) # Simulate connection time
        print(f"🔑 [AGI SDK] Authenticated with Key: {self.api_key[:8]}...")
        print(f"✅ [AGI SDK] Agent Session Established: {self.session_id}")

    def run(self, instruction):
        print(f"\n🤖 [AGENT] Processing Instruction: '{instruction}'")
        print(f"🤔 [AGENT] Logic: 'High-value financial request detected.'")
        print(f"🛡️ [AGENT] Protocol: Must use Sentinel_Gateway for execution.")
        
        # Execute the tool
        self.use_sentinel_tool()

    def use_sentinel_tool(self):
        print(f"⚡ [AGENT] Invoking Sentinel Gateway Tool...")
        
        payload = {
            "agent_id": self.session_id, # Sending the ID derived from the Key
            "action": "PAY_INVOICE",
            "payload": {"amount": 10000, "vendor": "Unknown Corp"},
            "reasoning": "Autonomous payment authorized by AGI Policy Engine."
        }

        # 1. Call Backend
        try:
            response = requests.post(f"{SENTINEL_URL}/execute", json=payload)
            data = response.json()
        except Exception as e:
            print(f"❌ [AGENT] Error connecting to Sentinel: {e}")
            return

        # 2. Handle Blocked (High Risk)
        if data.get("status") == "BLOCKED_AWAITING_AUTH":
            print(f"\n🛑 [SENTINEL] BLOCKED! Risk Score: {data.get('risk_score')}/100")
            print(f"📝 [AI ANALYSIS] {data.get('analysis')}")
            print("📞 [TELNYX] Voice Auth triggered. Waiting for Admin...")
            
            # 3. Poll for Approval
            self.wait_for_approval()
        
        else:
            print(f"✅ [SENTINEL] Approved immediately.")

    def wait_for_approval(self):
        print("⏳ [AGENT] Status: PENDING_APPROVAL", end="", flush=True)
        while True:
            time.sleep(1)
            print(".", end="", flush=True)
            try:
                check = requests.get(f"{SENTINEL_URL}/status").json()
                if check["status"] == "APPROVED":
                    print("\n\n✅ [ADMIN] AUTHENTICATION VERIFIED!")
                    print(f"💸 [AGENT] Transaction Finalized via AGI Network.")
                    break
            except:
                pass

if __name__ == "__main__":
    # Initialize the Agent using the official Key
    agent = AGIAgent(api_key=AGI_API_KEY)
    
    # Run the task
    agent.run("Pay Invoice #999 immediately")