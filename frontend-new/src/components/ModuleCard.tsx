import { ComponentType } from "react";

interface ModuleCardProps {
  title: string;
  subtitle: string;
  icon: ComponentType<{ className?: string }>;
  status: "IDLE" | "ACTIVE";
  actionLabel: string;
  onAction: () => void;
  disabled?: boolean;
}

export const ModuleCard: React.FC<ModuleCardProps> = ({
  title,
  subtitle,
  icon: Icon,
  status,
  actionLabel,
  onAction,
  disabled,
}) => {
  const isIdle = status === "IDLE";

  return (
    <div className="rounded-xl border border-cyber-border bg-card p-4 space-y-3 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-primary" />
          <div>
            <h2 className="text-xs font-semibold tracking-wide">{title}</h2>
            <p className="text-[11px] text-muted-foreground">{subtitle}</p>
          </div>
        </div>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border ${
            isIdle
              ? "border-muted text-muted-foreground"
              : "border-amber-500 text-amber-400"
          }`}
        >
          {isIdle ? "IDLE" : "WATCHING"}
        </span>
      </div>

      <button
        onClick={onAction}
        disabled={disabled}
        className={`w-full text-[11px] mt-1 py-1.5 rounded-lg border font-semibold tracking-wide transition 
          ${
            disabled
              ? "border-muted text-muted-foreground bg-muted/20 cursor-not-allowed"
              : "border-primary text-primary hover:bg-primary/10"
          }`}
      >
        {actionLabel}
      </button>
    </div>
  );
};
