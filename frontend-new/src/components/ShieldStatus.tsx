import { Shield, AlertTriangle, CheckCircle2, Activity } from "lucide-react";

type StatusType = "IDLE" | "MONITORING" | "ANALYZING" | "BLOCKED" | "APPROVED";

interface ShieldStatusProps {
  status: StatusType;
}

export const ShieldStatus = ({ status }: ShieldStatusProps) => {
  const configs = {
    IDLE: {
      color: "border-status-idle",
      shadow: "shadow-glow-blue",
      glow: "0 0 50px rgba(59, 130, 246, 0.3)",
      text: "SYSTEM MONITORING",
      icon: Shield,
      animate: "animate-pulse-glow",
    },
    MONITORING: {
      color: "border-status-monitoring",
      shadow: "shadow-glow-green",
      glow: "0 0 50px rgba(0, 255, 0, 0.3)",
      text: "AGENT ACTIVE",
      icon: Activity,
      animate: "animate-pulse",
    },
    ANALYZING: {
      color: "border-status-analyzing",
      shadow: "shadow-glow-amber",
      glow: "0 0 50px rgba(251, 191, 36, 0.3)",
      text: "ANALYZING INTENT...",
      icon: Activity,
      animate: "animate-spin-slow",
    },
    BLOCKED: {
      color: "border-status-blocked",
      shadow: "shadow-glow-red",
      glow: "0 0 100px rgba(239, 68, 68, 0.5)",
      text: "INTERVENTION REQUIRED",
      icon: AlertTriangle,
      animate: "animate-flicker",
    },
    APPROVED: {
      color: "border-status-approved",
      shadow: "shadow-glow-green",
      glow: "0 0 100px rgba(0, 255, 0, 0.5)",
      text: "ACTION AUTHORIZED",
      icon: CheckCircle2,
      animate: "",
    },
  };

  const config = configs[status];
  const Icon = config.icon;

  return (
    <div className="flex flex-col items-center justify-center">
      <div
        className={`w-64 h-64 rounded-full border-4 flex items-center justify-center transition-all duration-500 ${config.color} ${config.shadow} ${config.animate}`}
        style={{ boxShadow: config.glow }}
      >
        <div className="flex flex-col items-center gap-4">
          <Icon className="w-16 h-16" />
          <span className="text-xl font-bold tracking-widest text-center px-4">
            {config.text}
          </span>
        </div>
      </div>
    </div>
  );
};
