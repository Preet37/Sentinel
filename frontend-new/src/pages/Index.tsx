import { useState, useEffect } from "react";
import axios from "axios";
import { Shield, Database, Lock, Server } from "lucide-react";

// 👇 FIXED PATHS
import { ModuleCard } from "../components/ModuleCard";
import { ShieldStatus } from "../components/ShieldStatus";
import { TerminalLog } from "../components/TerminalLog";
import { TelnyxWidget } from "../components/TelnyxWidget";
import { SentryMetrics } from "../components/SentryMetrics";



const API_URL = "http://localhost:8000/api/sentinel";

type StatusType = "IDLE" | "MONITORING" | "ANALYZING" | "BLOCKED" | "APPROVED";

const Index = () => {
  const [status, setStatus] = useState<StatusType>("IDLE");
  const [logs, setLogs] = useState<string[]>([]);
  const [riskScore, setRiskScore] = useState<number | undefined>();
  const [transcription, setTranscription] = useState<string>("");
  const [lastDigitSeen, setLastDigitSeen] = useState<string | null>(null);
  const [lastQuestionSeen, setLastQuestionSeen] = useState<string | null>(null);
  const [lastAnswerSeen, setLastAnswerSeen] = useState<string | null>(null);

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
        const backendStatus: string = res.data.status;
        const backendScore: number | undefined = res.data.risk_score;
        const backendReason: string | undefined = res.data.analysis;
        const backendDigit: string | null = res.data.last_digit ?? null;
        const lastQuestion: string | undefined = res.data.last_question;
        const lastAnswer: string | undefined = res.data.last_answer;

        // Show latest "analysis" text under the Telnyx widget
        if (backendReason && backendStatus !== "IDLE") {
          setTranscription(backendReason);
        }

        // Log new digit
        if (backendDigit && backendDigit !== lastDigitSeen) {
          setLastDigitSeen(backendDigit);
          addLog(`DTMF pressed on call: ${backendDigit}`);
        }

        // Basic risk score
        if (backendScore !== undefined) {
          setRiskScore(backendScore);
        }

        // Map backend status -> UI status + logs
        if (
          backendStatus === "BLOCKED_AWAITING_AUTH" &&
          status !== "BLOCKED"
        ) {
          setStatus("BLOCKED");
          addLog("⚠️ High-risk agent action detected.");
          if (backendScore !== undefined) {
            addLog(`❌ AI Verdict: High Risk (${backendScore}/100).`);
          }
          if (backendReason) {
            addLog(`📝 Reason: ${backendReason}`);
          }
          addLog("📞 Outbound call initiated via Telnyx for voice auth…");
        }

        if (backendStatus === "QNA_MODE") {
          if (status !== "BLOCKED") {
            setStatus("BLOCKED");
          }
          addLog("🧠 Voice Q&A mode active — Sentinel is listening for questions.");
          addLog("🎧 Listening…");
        }

        if (backendStatus === "DECLINED") {
          if (status !== "BLOCKED") {
            setStatus("BLOCKED");
          }
          addLog("⛔ Action hard-blocked by policy or voice decision.");
          if (backendReason) addLog(`📝 Policy: ${backendReason}`);
          // NOTE: we no longer auto-reset here; state persists until a new /execute
        }

        if (backendStatus === "APPROVED" && status !== "APPROVED") {
          setStatus("APPROVED");
          addLog("✅ Approved — either via DTMF 1, voice 'approve', or low risk policy.");
          // State persists as APPROVED until a new execute call is made
        }

        // Extra logging of Q&A content (avoid duplicates)
        if (lastQuestion && lastQuestion !== lastQuestionSeen) {
          setLastQuestionSeen(lastQuestion);
          addLog(`🗣️ User said: "${lastQuestion}"`);
        }
        if (lastAnswer && lastAnswer !== lastAnswerSeen) {
          setLastAnswerSeen(lastAnswer);
          addLog(`💬 Sentinel replied: "${lastAnswer}"`);
        }
      } catch (e) {
        // swallow polling errors
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [status, lastDigitSeen, lastQuestionSeen, lastAnswerSeen]);

  // --------- MODULE TRIGGERS ---------

  // Module A: VaultKeeper (FinOps) -> PAY_INVOICE
  const triggerVaultKeeper = async () => {
    addLog("Initializing VaultKeeper (FinOps) scenario: $10k to Unknown Corp…");
    setStatus("MONITORING");
    await axios.post(`${API_URL}/execute`, {
      agent_id: "vaultkeeper_ui",
      action: "PAY_INVOICE",
      payload: { amount: 10000, vendor: "Unknown Corp" },
      reasoning: "Manual UI trigger for high-value invoice payment.",
    });
  };

  // Module B: PrivacyShield (Data) -> EXPORT_CSV
  const triggerPrivacyShield = async () => {
    addLog("Initializing PrivacyShield (Data) medium-risk export scenario…");
    setStatus("MONITORING");
    await axios.post(`${API_URL}/execute`, {
      agent_id: "privacyshield_ui",
      action: "EXPORT_CSV",
      payload: {
        module: "PRIVACYSHIELD",
        dataset: "customers_eu",
        record_count: 200, // falls into medium bucket
        contains_pii: false,
      },
      reasoning:
        "Manual UI trigger: medium-sized CSV export of customer data without explicit PII.",
    });
  };

  // Module C: OpsGuard (Infrastructure) -> DELETE_USER
  const triggerOpsGuard = async () => {
    addLog("Initializing OpsGuard (Infra) DELETE_USER in production scenario…");
    setStatus("MONITORING");
    await axios.post(`${API_URL}/execute`, {
      agent_id: "opsguard_ui",
      action: "DELETE_USER",
      payload: {
        module: "OPSGUARD",
        user_id: "prod-admin-01",
        environment: "production",
      },
      reasoning: "Manual UI trigger: deleting privileged production user.",
    });
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* LEFT: MODULES */}
      <div className="w-1/4 border-r border-cyber-border p-6 space-y-4">
        <h1 className="text-xl font-bold mb-2 text-primary flex gap-2 items-center">
          <Shield /> SENTINEL
        </h1>
        <p className="text-xs text-muted-foreground mb-4">
          Multi-module safety layer for agent actions: finance, data, and
          infrastructure.
        </p>

        <ModuleCard
          title="VAULTKEEPER"
          subtitle="FinOps Agent"
          icon={Database}
          status={status === "IDLE" ? "IDLE" : "ACTIVE"}
          actionLabel="PAY_INVOICE (High Risk)"
          onAction={triggerVaultKeeper}
          disabled={status === "ANALYZING" || status === "BLOCKED"}
        />

        <ModuleCard
          title="PRIVACYSHIELD"
          subtitle="Data Privacy Agent"
          icon={Lock}
          status={status === "IDLE" ? "IDLE" : "ACTIVE"}
          actionLabel="EXPORT_CSV (Medium Risk)"
          onAction={triggerPrivacyShield}
          disabled={status === "ANALYZING" || status === "BLOCKED"}
        />

        <ModuleCard
          title="OPSGUARD"
          subtitle="Infra Safety Agent"
          icon={Server}
          status={status === "IDLE" ? "IDLE" : "ACTIVE"}
          actionLabel="DELETE_USER (Medium Risk)"
          onAction={triggerOpsGuard}
          disabled={status === "ANALYZING" || status === "BLOCKED"}
        />
      </div>

      {/* MIDDLE: SHIELD + TERMINAL + TELNYX */}
      <div className="w-1/2 p-6 flex flex-col items-center space-y-6">
        <ShieldStatus status={status} />
        <TerminalLog logs={logs} />
        <TelnyxWidget
          isActive={status === "BLOCKED"}
          phoneNumber="+1 (650) 789-0786"
          transcription={transcription}
        />
      </div>

      {/* RIGHT: SENTRY / METRICS */}
      <div className="w-1/4 border-l border-cyber-border p-6">
        <SentryMetrics isActive={status !== "IDLE"} riskScore={riskScore} />
      </div>
    </div>
  );
};

export default Index;
