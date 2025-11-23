import { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

interface ModuleCardProps {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  status: "IDLE" | "PROTECTED" | "ACTIVE";
  actionLabel: string;
  onAction: () => void;
  disabled?: boolean;
}

export const ModuleCard = ({
  title,
  subtitle,
  icon: Icon,
  status,
  actionLabel,
  onAction,
  disabled,
}: ModuleCardProps) => {
  const statusColors = {
    IDLE: "text-muted-foreground",
    PROTECTED: "text-status-monitoring",
    ACTIVE: "text-status-analyzing",
  };

  return (
    <Card className="bg-cyber-surface border-cyber-border p-4 hover:border-primary/50 transition-all">
      <div className="flex items-start gap-3 mb-4">
        <div className="p-2 rounded bg-primary/10 border border-primary/20">
          <Icon className="w-6 h-6 text-primary" />
        </div>
        <div className="flex-1">
          <h3 className="font-bold text-sm tracking-wider">{title}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
        </div>
      </div>
      
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-bold tracking-widest text-muted-foreground">STATUS</span>
        <span className={`text-[10px] font-bold tracking-widest ${statusColors[status]}`}>
          {status}
        </span>
      </div>

      <Button
        onClick={onAction}
        disabled={disabled}
        variant="outline"
        className="w-full bg-destructive/10 border-destructive/30 hover:bg-destructive/20 hover:border-destructive text-destructive text-xs font-bold tracking-wide"
      >
        {actionLabel}
      </Button>
    </Card>
  );
};
