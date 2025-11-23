import { ShieldAlert, ShieldCheck, Loader2, PauseCircle } from "lucide-react";

type StatusType = "IDLE" | "MONITORING" | "ANALYZING" | "BLOCKED" | "APPROVED";

interface ShieldStatusProps {
  status: StatusType;
}

export const ShieldStatus: React.FC<ShieldStatusProps> = ({ status }) => {
  let icon = <PauseCircle className="w-6 h-6" />;
  let label = "Idle — Waiting for agent actions.";
  let color = "text-muted-foreground";

  if (status === "MONITORING") {
    icon = <Loader2 className="w-6 h-6 animate-spin" />;
    label = "Monitoring an active agent action…";
    color = "text-amber-400";
  } else if (status === "ANALYZING") {
    icon = <Loader2 className="w-6 h-6 animate-spin" />;
    label = "Analyzing risk with Sentinel + Groq…";
    color = "text-sky-400";
  } else if (status === "BLOCKED") {
    icon = <ShieldAlert className="w-6 h-6" />;
    label = "Action blocked — waiting for voice decision.";
    color = "text-red-400";
  } else if (status === "APPROVED") {
    icon = <ShieldCheck className="w-6 h-6" />;
    label = "Approved — Sentinel cleared this action.";
    color = "text-emerald-400";
  }

  return (
    <div className="w-full max-w-xl rounded-xl border border-cyber-border bg-card px-4 py-3 flex items-center gap-3 shadow-sm">
      <div className={color}>{icon}</div>
      <div className="flex flex-col">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Sentinel Shield Status
        </span>
        <span className="text-xs">{label}</span>
      </div>
    </div>
  );
};
