import { PhoneCall, Mic } from "lucide-react";

interface TelnyxWidgetProps {
  isActive: boolean;
  phoneNumber: string;
  transcription: string;
}

export const TelnyxWidget: React.FC<TelnyxWidgetProps> = ({
  isActive,
  phoneNumber,
  transcription,
}) => {
  return (
    <div className="w-full max-w-xl rounded-xl border border-cyber-border bg-card p-4 space-y-3 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <PhoneCall className="w-4 h-4 text-primary" />
          <span className="text-xs font-semibold tracking-wide">
            TELNYX VOICE GUARD
          </span>
        </div>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border ${
            isActive
              ? "border-emerald-500 text-emerald-400"
              : "border-muted text-muted-foreground"
          }`}
        >
          {isActive ? "ON-CALL AUTH FLOW" : "IDLE"}
        </span>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Admin: {phoneNumber}</span>
        <div className="flex items-center gap-1">
          <Mic className="w-3 h-3" />
          <span>{isActive ? "Listening for approval…" : "Waiting for trigger"}</span>
        </div>
      </div>

      {transcription && (
        <div className="mt-2 text-xs bg-background/60 border border-cyber-border rounded-lg px-3 py-2 font-mono">
          <span className="block text-[10px] uppercase text-muted-foreground mb-1">
            Sentinel Analysis
          </span>
          <p className="leading-snug">{transcription}</p>
        </div>
      )}
    </div>
  );
};
