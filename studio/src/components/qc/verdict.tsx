import { cn } from "@/lib/utils";
import type { Verdict } from "@/lib/types";

type Style = { label: string; dot: string; text: string; bg: string; border: string };

export const VERDICT_STYLES: Record<Verdict, Style> = {
  pass: {
    label: "Pass",
    dot: "bg-emerald-500",
    text: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
  },
  warn: {
    label: "Warn",
    dot: "bg-amber-500",
    text: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
  },
  fail: {
    label: "Fail",
    dot: "bg-red-500",
    text: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
  },
};

export const SEVERITY_STYLES: Record<string, { text: string; bg: string; border: string }> = {
  high: { text: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/30" },
  medium: { text: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/30" },
  low: { text: "text-sky-400", bg: "bg-sky-500/10", border: "border-sky-500/30" },
  none: { text: "text-muted-foreground", bg: "bg-muted", border: "border-border" },
};

export function VerdictPill({
  verdict,
  className,
}: {
  verdict: Verdict;
  className?: string;
}) {
  const s = VERDICT_STYLES[verdict];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        s.bg,
        s.border,
        s.text,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

export function SeverityPill({ severity }: { severity: string }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.none;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
        s.bg,
        s.border,
        s.text,
      )}
    >
      {severity}
    </span>
  );
}

export const pct = (x: number): string => `${(x * 100).toFixed(1)}%`;
