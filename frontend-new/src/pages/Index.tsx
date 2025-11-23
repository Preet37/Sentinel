import { useState, useEffect } from "react";
import axios from "axios";
import { Shield, Database } from "lucide-react";
import { ModuleCard } from "@/components/ModuleCard";
import { ShieldStatus } from "@/components/ShieldStatus";
import { TerminalLog } from "@/components/TerminalLog";
import { TelnyxWidget } from "@/components/TelnyxWidget";
import { SentryMetrics } from "@/components/SentryMetrics";

const API_URL = "http://localhost:8000/api/sentinel";

type StatusType = "IDLE" | "MONITORING" | "ANALYZING" | "BLOCKED" | "APPROVED";

const Index = () => {
  const [status, setStatus] = useState<StatusType>("IDLE");
  const [logs, setLogs] = useState<string[]>([]);
  const [riskScore, setRiskScore] = useState<number | undefined>();
  const [transcription, setTranscription] = useState<string>("");

  const addLog = (msg: string) => {
    setLogs((prev) => {
        // Don't duplicate logs
        if (prev.length > 0 && prev[0] === `> ${msg}`) return prev;
        return [`> ${msg}`, ...prev];
    });
  };

  // --- GLOBAL WATCHER (THE MAGIC SAUCE) ---
  // This constantly asks the backend: "What is happening?"
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API_URL}/status`);
        const backendStatus = res.data.status;
        const backendScore = res.data.risk_score;
        const backendReason = res.data.analysis;

        // 1. DETECT ATTACK START
        if (backendStatus === "BLOCKED_AWAITING_AUTH" && status !== "BLOCKED") {
            setStatus("BLOCKED");
            setRiskScore(backendScore);
            addLog(`⚠️ INCOMING AGENT REQUEST DETECTED`);
            addLog(`❌ AI Verdict: High Risk (${backendScore}/100)`);
            addLog(`📝 Reason: ${backendReason}`);
            addLog(`📞 Call initiated via Telnyx...`);
        }

        // 2. DETECT APPROVAL (When you press 1)
        if (backendStatus === "APPROVED" && status === "BLOCKED") {
            setStatus("APPROVED");
            addLog("✅ VOICE AUTH VERIFIED: '1' Pressed");
            setTranscription("ACCESS GRANTED");
            
            // Reset after 5 seconds
            setTimeout(() => {
                setStatus("IDLE");
                setRiskScore(undefined);
                setTranscription("");
                setLogs([]);
            }, 5000);
        }

      } catch (e) { 
          // console.error("Polling error:", e); 
      }
    }, 1000); // Poll every 1 second

    return () => clearInterval(interval);
  }, [status]);

  // --- Manual Trigger (Optional now, since Agent.py does it) ---
  const simulateAttack = async () => {
    addLog("Initializing Sentinel Platform...");
    setStatus("MONITORING");
    await axios.post(`${API_URL}/execute`, {
        agent_id: "demo_ui",
        action: "PAY_INVOICE",
        payload: { amount: 10000, vendor: "Unknown" }, 
        reasoning: "Manual UI Trigger"
    });
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <div className="w-1/4 border-r border-cyber-border p-6">
        <h1 className="text-xl font-bold mb-6 text-primary flex gap-2"><Shield/> SENTINEL</h1>
        <ModuleCard
          title="VAULTKEEPER" subtitle="FinOps Agent" icon={Database}
          status={status === "IDLE" ? "IDLE" : "ACTIVE"}
          actionLabel="MANUAL TRIGGER"
          onAction={simulateAttack}
          disabled={status !== "IDLE"}
        />
      </div>

      <div className="w-1/2 p-6 flex flex-col items-center space-y-6">
        <ShieldStatus status={status} />
        <TerminalLog logs={logs} />
        <TelnyxWidget isActive={status === "BLOCKED"} phoneNumber="+1 (650) 789-0786" transcription={transcription} />
      </div>

      <div className="w-1/4 border-l border-cyber-border p-6">
        <SentryMetrics isActive={status !== "IDLE"} riskScore={riskScore} />
      </div>
    </div>
  );
};

export default Index;