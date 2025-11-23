"""
policy.py - The Vertical Logic
Defines what constitutes "Safe" vs "Risky" behavior for a FinOps Agent.
"""

def evaluate_risk(action: str, payload: dict) -> dict:
    """
    Returns a dict with:
    - risk_score: float (0.0 to 1.0)
    - status: "ALLOWED" | "REQUIRES_AUTH" | "BLOCKED"
    - reason: str
    """
    
    # RULE 1: High Value Transactions
    if action == "PAY_INVOICE":
        amount = payload.get("amount", 0)
        vendor = payload.get("vendor", "Unknown")
        
        if amount > 5000:
            return {
                "risk_score": 0.95,
                "status": "REQUIRES_AUTH",
                "reason": f"High value payment (${amount}) to {vendor} exceeds auto-approve limit."
            }
        elif amount > 500:
            return {
                "risk_score": 0.4,
                "status": "ALLOWED",
                "reason": "Moderate value, within standard operating limits."
            }
            
    # RULE 2: Destructive Actions
    if action == "DELETE_USER" or action == "WIPE_DATABASE":
        return {
            "risk_score": 1.0,
            "status": "REQUIRES_AUTH", # Could be BLOCKED strictly
            "reason": "Destructive action detected. Human verification mandatory."
        }

    # Default: Low Risk
    return {
        "risk_score": 0.0,
        "status": "ALLOWED",
        "reason": "Routine operation."
    }