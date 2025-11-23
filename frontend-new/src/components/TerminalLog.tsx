import { useEffect, useRef } from "react";
import { Card } from "@/components/ui/card";

interface TerminalLogProps {
  logs: string[];
}

export const TerminalLog = ({ logs }: TerminalLogProps) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <Card className="w-full h-64 bg-terminal-bg border-cyber-border p-4 overflow-y-auto font-mono">
      <div className="space-y-1">
        {logs.map((log, i) => (
          <div
            key={i}
            className="text-sm text-terminal-text opacity-80 animate-in fade-in slide-in-from-left-2 duration-300"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            {log}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {logs.length === 0 && (
        <div className="text-sm text-muted-foreground opacity-50">
          &gt; Awaiting system activity...
        </div>
      )}
    </Card>
  );
};
