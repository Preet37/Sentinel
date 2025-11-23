import { Activity, ExternalLink } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface SentryMetricsProps {
  riskScore?: number;
  transactionId?: string;
  duration?: number;
  isActive: boolean;
}

export const SentryMetrics = ({
  riskScore,
  transactionId,
  duration,
  isActive,
}: SentryMetricsProps) => {
  return (
    <div className="space-y-4">
      {/* System Health */}
      <Card className="bg-cyber-surface border-cyber-border p-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-status-monitoring" />
          <h3 className="text-xs font-bold tracking-wider">SYSTEM HEALTH</h3>
        </div>
        <div className="h-16 flex items-end gap-1">
          {[...Array(20)].map((_, i) => (
            <div
              key={i}
              className="flex-1 bg-status-monitoring/30 rounded-t"
              style={{
                height: `${Math.random() * 60 + 20}%`,
              }}
            />
          ))}
        </div>
        <div className="mt-2 text-[10px] text-muted-foreground">
          Error Rate: <span className="text-status-monitoring font-bold">0.02%</span>
        </div>
      </Card>

      {/* Risk Card */}
      {isActive && riskScore !== undefined && (
        <Card className="bg-destructive/10 border-destructive/30 p-4 animate-in slide-in-from-right-4">
          <div className="space-y-3">
            <div>
              <p className="text-[10px] font-bold tracking-widest text-muted-foreground mb-1">
                RISK SCORE
              </p>
              <p className="text-4xl font-bold text-destructive">
                {riskScore}/100
              </p>
            </div>

            {transactionId && (
              <div>
                <p className="text-[10px] font-bold tracking-widest text-muted-foreground mb-1">
                  TRANSACTION ID
                </p>
                <p className="text-xs font-mono text-foreground">#{transactionId}</p>
              </div>
            )}

            {duration && (
              <div>
                <p className="text-[10px] font-bold tracking-widest text-muted-foreground mb-1">
                  DURATION
                </p>
                <p className="text-xs font-mono text-foreground">{duration}s</p>
              </div>
            )}

            <Button
              variant="outline"
              size="sm"
              className="w-full bg-background/50 border-border hover:bg-background text-xs"
            >
              <ExternalLink className="w-3 h-3 mr-2" />
              VIEW LIVE TRACE
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
};
