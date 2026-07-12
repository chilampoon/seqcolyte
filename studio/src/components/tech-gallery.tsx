"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TechIndexEntry } from "@/lib/technologies";

function tally(values: (string | null | undefined)[]): [string, number][] {
  const m = new Map<string, number>();
  for (const v of values) if (v) m.set(v, (m.get(v) ?? 0) + 1);
  return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function FilterRow({
  label,
  counts,
  active,
  onPick,
}: {
  label: string;
  counts: [string, number][];
  active: string | null;
  onPick: (v: string | null) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-muted-foreground mr-1 text-xs font-medium">{label}</span>
      <button
        onClick={() => onPick(null)}
        className={cn(
          "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
          active === null ? "border-primary/50 bg-primary/10 text-foreground" : "border-border/60 text-muted-foreground hover:text-foreground",
        )}
      >
        All
      </button>
      {counts.map(([v, n]) => (
        <button
          key={v}
          onClick={() => onPick(active === v ? null : v)}
          className={cn(
            "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
            active === v ? "border-primary/50 bg-primary/10 text-foreground" : "border-border/60 text-muted-foreground hover:text-foreground",
          )}
        >
          {v} <span className="opacity-60">{n}</span>
        </button>
      ))}
    </div>
  );
}

function TechCard({ t }: { t: TechIndexEntry }) {
  return (
    <Link href={`/technologies/${t.id}`} className="group block">
      <Card className="group-hover:border-primary/50 h-full transition-colors">
        <CardHeader>
          <CardTitle className="text-base leading-tight">{t.title ?? t.id}</CardTitle>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {t.modality && (
              <Badge className="border-transparent bg-sky-500/15 text-[10px] text-sky-600 dark:text-sky-400">
                {t.modality}
              </Badge>
            )}
            {t.method_type && (
              <Badge className="border-transparent bg-violet-500/15 text-[10px] text-violet-600 dark:text-violet-400">
                {t.method_type}
              </Badge>
            )}
            {t.platform && (
              <Badge variant="secondary" className="text-[10px]">
                {t.platform}
              </Badge>
            )}
          </div>
          {t.description && <CardDescription className="line-clamp-3 pt-1">{t.description}</CardDescription>}
        </CardHeader>
      </Card>
    </Link>
  );
}

export function TechGallery({ techs }: { techs: TechIndexEntry[] }) {
  const [mod, setMod] = useState<string | null>(null);
  const [meth, setMeth] = useState<string | null>(null);

  const modCounts = useMemo(() => tally(techs.map((t) => t.modality)), [techs]);
  const methCounts = useMemo(() => tally(techs.map((t) => t.method_type)), [techs]);

  const filtered = techs.filter(
    (t) => (!mod || t.modality === mod) && (!meth || t.method_type === meth),
  );
  // when no modality filter is active, group the grid by modality (ordered by size)
  const groups: [string, TechIndexEntry[]][] = mod
    ? [[mod, filtered]]
    : modCounts
        .map(([m]) => [m, filtered.filter((t) => t.modality === m)] as [string, TechIndexEntry[]])
        .filter(([, items]) => items.length > 0);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <FilterRow label="Modality" counts={modCounts} active={mod} onPick={setMod} />
        <FilterRow label="Method" counts={methCounts} active={meth} onPick={setMeth} />
      </div>
      {filtered.length === 0 ? (
        <p className="text-muted-foreground text-sm">No technologies match those filters.</p>
      ) : (
        groups.map(([g, items]) => (
          <section key={g}>
            {!mod && (
              <h2 className="text-muted-foreground mb-3 text-xs font-medium tracking-wide uppercase">
                {g} <span className="opacity-60">{items.length}</span>
              </h2>
            )}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((t) => (
                <TechCard key={t.id} t={t} />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
