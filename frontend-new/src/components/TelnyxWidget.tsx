import { Phone, Mic } from "lucide-react";
import { Card } from "@/components/ui/card";

interface TelnyxWidgetProps {
  phoneNumber?: string;
  transcription?: string;
  isActive: boolean;
}

export const TelnyxWidget = ({
  phoneNumber = "+1 (555) XXX-XXXX",
  transcription,
  isActive,
}: TelnyxWidgetProps) => {
  if (!isActive) return null;

  return (
    <Card className="bg-destructive/10 border-destructive/30 p-6 mt-4 animate-in slide-in-from-bottom-4">
      <div className="flex items-center gap-4 mb-4">
        <div className="relative">
          <div className="absolute inset-0 bg-destructive/20 rounded-full animate-ping" />
          <Phone className="w-8 h-8 text-destructive relative z-10 animate-pulse" />
        </div>
        <div>
          <p className="text-xs font-bold tracking-wider text-destructive-foreground opacity-70">
            CALLING ADMINISTRATOR
          </p>
          <p className="text-sm font-mono text-destructive-foreground">{phoneNumber}</p>
        </div>
      </div>

      {/* Sound waves animation */}
      <div className="flex justify-center gap-1 mb-4">
        {[...Array(8)].map((_, i) => (
          <div
            key={i}
            className="w-1 bg-destructive rounded-full animate-pulse"
            style={{
              height: `${Math.random() * 32 + 16}px`,
              animationDelay: `${i * 100}ms`,
            }}
          />
        ))}
      </div>

      {transcription && (
        <div className="mt-4 p-3 bg-terminal-bg rounded border border-cyber-border">
          <div className="flex items-center gap-2 mb-2">
            <Mic className="w-4 h-4 text-status-monitoring" />
            <span className="text-xs font-bold tracking-wider text-status-monitoring">
              VOICE DETECTED
            </span>
          </div>
          <p className="text-sm font-mono text-foreground">&quot;{transcription}&quot;</p>
        </div>
      )}
    </Card>
  );
};
