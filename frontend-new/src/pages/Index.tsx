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
  const [lastDigit, setLastDigit] = useState<string | null>(null);

  const addLog = (msg: string) => {
    setLogs((prev) => {
      if (prev.length > 0 && prev[0] === `> ${msg}`) return prev;
      return [`> ${msg}`, ...prev];
    });
  };

  // --- GLOBAL WATCHER ---
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API_URL}/status`);
        const backendStatus = res.data.status as string;
        const backendScore = res.data.risk_score as number;
        const backendReason = res.data.analysis as string;
        const backendDigit = res.data.last_digit as string | null;

        // 1. Detect high-risk event / blocking
        if (backendStatus === "BLOCKED_AWAITING_AUTH" && status !== "BLOCKED") {
          setStatus("BLOCKED");
          setRiskScore(backendScore);
          addLog(`⚠️ INCOMING AGENT REQUEST DETECTED`);
          addLog(`❌ AI Verdict: High Risk (${backendScore}/100)`);
          addLog(`📝 Reason: ${backendReason}`);
          addLog(`📞 Call initiated via Telnyx...`);
        }

        // 2. Detect new digit press
        if (backendDigit && backendDigit !== lastDigit) {
          setLastDigit(backendDigit);
          addLog(`🔢 Admin pressed: ${backendDigit}`);
          setTranscription(`Admin pressed: ${backendDigit}`);
        }

        // 3. Detect Approval
        if (backendStatus === "APPROVED" && status === "BLOCKED") {
          setStatus("APPROVED");
          addLog("✅ VOICE AUTH VERIFIED: Transaction Approved");
          setTranscription(
            "Thank you for approving this transaction. Access granted."
          );

          setTimeout(() => {
            setStatus("IDLE");
            setRiskScore(undefined);
            setTranscription("");
            setLogs([]);
            setLastDigit(null);
          }, 5000);
        }

        // 4. Detect Decline
        if (backendStatus === "DECLINED" && status === "BLOCKED") {
          addLog("🛑 VOICE AUTH: Transaction Declined");
          setTranscription(
            "The transaction has been declined. Sentinel will block this."
          );

          setTimeout(() => {
            setStatus("IDLE");
            setRiskScore(undefined);
            setTranscription("");
            setLogs([]);
            setLastDigit(null);
          }, 5000);
        }
      } catch (e) {
        // silent for now
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [status, lastDigit]);

  // --- Manual Trigger (Optional) ---
  const simulateAttack = async () => {
    addLog("Initializing Sentinel Platform...");
    setStatus("MONITORING");
    await axios.post(`${API_URL}/execute`, {
      agent_id: "demo_ui",
      action: "PAY_INVOICE",
      payload: { amount: 10000, vendor: "Unknown" },
      reasoning: "Manual UI Trigger",
    });
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* LEFT: control panel */}
      <div className="w-1/4 border-r border-cyber-border p-6">
        <h1 className="text-xl font-bold mb-6 text-primary flex gap-2">
          <Shield /> SENTINEL
        </h1>
        <ModuleCard
          title="VAULTKEEPER"
          subtitle="FinOps Agent"
          icon={Database}
          status={status === "IDLE" ? "IDLE" : "ACTIVE"}
          actionLabel="MANUAL TRIGGER"
          onAction={simulateAttack}
          disabled={status !== "IDLE"}
        />
      </div>

      {/* MIDDLE: status + logs */}
      <div className="w-1/2 p-6 flex flex-col items-center space-y-6">
        <ShieldStatus status={status} />
        <TerminalLog logs={logs} />
        <TelnyxWidget
          isActive={status === "BLOCKED"}
          phoneNumber="+1 (650) 789-0786"
          transcription={transcription}
        />
      </div>

      {/* RIGHT: Sentry metrics */}
      <div className="w-1/4 border-l border-cyber-border p-6">
        <SentryMetrics isActive={status !== "IDLE"} riskScore={riskScore} />
      </div>
    </div>
  );
};

export default Index;
