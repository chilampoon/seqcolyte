"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type {
  DiagCause,
  DiagIssue,
  DiagSignal,
  DiagTest,
  DiagnosticCatalog,
} from "@/lib/diagnostics";

/** Theme-safe accent classes for a diagnostic test's implementation status. */
function tone(kind: string): string {
  const map: Record<string, string> = {
    implemented: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
    planned: "bg-muted text-muted-foreground",
    external: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  };
  return map[kind] ?? "bg-muted text-muted-foreground";
}

const short = (id: string) => (id.includes(".") ? id.slice(id.indexOf(".") + 1) : id);

function FilterRow({
  label,
  options,
  active,
  onPick,
}: {
  label: string;
  options: string[];
  active: string | null;
  onPick: (v: string | null) => void;
}) {
  if (options.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-muted-foreground mr-1 w-28 shrink-0 text-sm font-medium">{label}</span>
      <button
        onClick={() => onPick(null)}
        className={cn(
          "rounded-full border px-3 py-0.5 text-sm transition-colors",
          active === null
            ? "border-primary/50 bg-primary/10 text-foreground"
            : "border-border/60 text-muted-foreground hover:text-foreground",
        )}
      >
        All
      </button>
      {options.map((v) => (
        <button
          key={v}
          onClick={() => onPick(active === v ? null : v)}
          className={cn(
            "rounded-full border px-3 py-0.5 text-sm transition-colors",
            active === v
              ? "border-primary/50 bg-primary/10 text-foreground"
              : "border-border/60 text-muted-foreground hover:text-foreground",
          )}
        >
          {v}
        </button>
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground text-sm font-medium tracking-wide uppercase">{label}</div>
      <div className="text-base">{children}</div>
    </div>
  );
}

function IssueDetail({
  issue,
  signals,
  causes,
  tests,
}: {
  issue: DiagIssue;
  signals: Record<string, DiagSignal>;
  causes: Record<string, DiagCause>;
  tests: Record<string, DiagTest>;
}) {
  return (
    <div className="space-y-5">
      <h3 className="text-lg font-semibold tracking-tight">{issue.title}</h3>
      <p className="text-muted-foreground text-base">{issue.summary}</p>

      <Field label="Observable signals">
        <ul className="space-y-1">
          {issue.supporting_signals.map((s) => {
            const sig = signals[s];
            const plats = sig?.platforms ?? [];
            // tag a signal only when it is platform-specific (not the cross-platform illumina+nanopore case)
            const universal = plats.includes("illumina") && plats.includes("nanopore");
            const tag = !universal && plats.length ? plats.join(" / ") : null;
            return (
              <li key={s} className="flex flex-wrap items-center gap-2">
                <span>{sig?.label ?? s}</span>
                {tag && (
                  <Badge variant="secondary" className="text-[10px]">
                    {tag}
                  </Badge>
                )}
              </li>
            );
          })}
        </ul>
      </Field>

      <Field label="Candidate root causes">
        <div className="space-y-2">
          {issue.candidate_root_causes.map((cid) => {
            const c = causes[cid];
            if (!c) return <div key={cid}>{cid}</div>;
            return (
              <div key={cid} className="border-border/60 rounded-md border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{c.title}</span>
                  {c.workflow_stage && (
                    <Badge variant="secondary" className="text-[10px]">
                      {c.workflow_stage.replace(/_/g, " ")}
                    </Badge>
                  )}
                </div>
                <p className="text-muted-foreground mt-1 text-sm">{c.mechanism}</p>
              </div>
            );
          })}
        </div>
      </Field>

      <Field label="Confirmatory tests">
        <ul className="space-y-1">
          {issue.confirmatory_tests.map((tid) => {
            const t = tests[tid];
            return (
              <li key={tid} className="flex flex-wrap items-center gap-2">
                <span>{t?.title ?? tid}</span>
                {t && (
                  <Badge variant="outline" className={cn("text-xs", tone(t.status))}>
                    {t.status}
                  </Badge>
                )}
              </li>
            );
          })}
        </ul>
      </Field>
    </div>
  );
}

export function DiagnosticWiki({ catalog }: { catalog: DiagnosticCatalog }) {
  const signals = useMemo(
    () => Object.fromEntries(catalog.signals.map((s) => [s.signal_id, s])) as Record<string, DiagSignal>,
    [catalog],
  );
  const causes = useMemo(
    () => Object.fromEntries(catalog.root_causes.map((c) => [c.cause_id, c])) as Record<string, DiagCause>,
    [catalog],
  );
  const tests = useMemo(
    () => Object.fromEntries(catalog.diagnostic_tests.map((t) => [t.test_id, t])) as Record<string, DiagTest>,
    [catalog],
  );

  const platforms = useMemo(() => [...new Set(catalog.issues.flatMap((i) => i.platforms))].sort(), [catalog]);
  const domains = useMemo(() => [...new Set(catalog.issues.flatMap((i) => i.outcome_domains))].sort(), [catalog]);

  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<string | null>(null);
  const [domain, setDomain] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return catalog.issues.filter((issue) => {
      if (platform && !issue.platforms.includes(platform)) return false;
      if (domain && !issue.outcome_domains.includes(domain)) return false;
      if (!q) return true;
      const hay = [
        issue.title,
        issue.summary,
        ...issue.candidate_root_causes.map((c) => causes[c]?.title ?? c),
        ...issue.supporting_signals.map((s) => signals[s]?.label ?? s),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [catalog, query, platform, domain, causes, signals]);

  const active = filtered.find((i) => i.issue_id === selected)?.issue_id ?? filtered[0]?.issue_id;

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold tracking-tight">
            Issue families <span className="text-muted-foreground">{filtered.length}</span>
          </h2>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search issues, causes, signals…"
            className="max-w-xs"
            aria-label="Search the diagnostic catalog"
          />
        </div>
        <div className="space-y-2">
          <FilterRow label="Platform" options={platforms} active={platform} onPick={setPlatform} />
          <FilterRow label="Outcome domain" options={domains} active={domain} onPick={setDomain} />
        </div>

        {filtered.length === 0 || !active ? (
          <p className="text-muted-foreground text-base">No issues match those filters.</p>
        ) : (
          <Tabs
            orientation="vertical"
            value={active}
            onValueChange={setSelected}
            className="items-start gap-6"
          >
            <TabsList variant="line" className="w-60 shrink-0 gap-1">
              {filtered.map((issue) => (
                <TabsTrigger
                  key={issue.issue_id}
                  value={issue.issue_id}
                  className="h-auto py-2 text-left text-sm whitespace-normal"
                >
                  {issue.title}
                </TabsTrigger>
              ))}
            </TabsList>
            <div className="min-w-0 flex-1">
              {filtered.map((issue) => (
                <TabsContent key={issue.issue_id} value={issue.issue_id} className="mt-0">
                  <IssueDetail issue={issue} signals={signals} causes={causes} tests={tests} />
                </TabsContent>
              ))}
            </div>
          </Tabs>
        )}
      </section>

      <Tabs defaultValue="matrix" className="space-y-3">
        <TabsList>
          <TabsTrigger value="matrix">Root-cause matrix</TabsTrigger>
          <TabsTrigger value="glossary">Metric glossary</TabsTrigger>
          <TabsTrigger value="coverage">Evidence coverage</TabsTrigger>
        </TabsList>
        <TabsContent value="matrix">
          <RootCauseMatrix catalog={catalog} />
        </TabsContent>
        <TabsContent value="glossary">
          <MetricGlossary catalog={catalog} />
        </TabsContent>
        <TabsContent value="coverage">
          <EvidenceCoverage catalog={catalog} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function RootCauseMatrix({ catalog }: { catalog: DiagnosticCatalog }) {
  const causes = catalog.root_causes;
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-sm whitespace-nowrap">issue \ cause</TableHead>
            {causes.map((c) => (
              <TableHead key={c.cause_id} className="text-sm whitespace-nowrap">
                {short(c.cause_id)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {catalog.issues.map((issue) => {
            const set = new Set(issue.candidate_root_causes);
            return (
              <TableRow key={issue.issue_id}>
                <TableCell className="text-muted-foreground text-sm whitespace-nowrap">
                  {short(issue.issue_id)}
                </TableCell>
                {causes.map((c) => (
                  <TableCell key={c.cause_id} className="text-center">
                    {set.has(c.cause_id) ? <span className="text-primary">●</span> : ""}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function MetricGlossary({ catalog }: { catalog: DiagnosticCatalog }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-sm">metric</TableHead>
            <TableHead className="text-sm">domain</TableHead>
            <TableHead className="text-sm">unit</TableHead>
            <TableHead className="text-sm">direction</TableHead>
            <TableHead className="text-sm">source aliases</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {catalog.metrics.map((m) => (
            <TableRow key={m.metric_id}>
              <TableCell className="align-top">
                <div className="font-mono text-sm">{m.metric_id}</div>
                <div className="text-muted-foreground text-sm">{m.description}</div>
              </TableCell>
              <TableCell className="align-top text-sm">{m.domain}</TableCell>
              <TableCell className="align-top text-sm">{m.unit}</TableCell>
              <TableCell className="align-top text-sm">{m.direction}</TableCell>
              <TableCell className="text-muted-foreground align-top text-sm">
                {(m.aliases ?? []).map((a) => a.label).join("; ") || "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function EvidenceCoverage({ catalog }: { catalog: DiagnosticCatalog }) {
  const byScope = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const metric of catalog.metrics) {
      for (const scope of metric.required_scopes) {
        (m[scope] ??= []).push(metric.metric_id);
      }
    }
    return Object.entries(m).sort((a, b) => a[0].localeCompare(b[0]));
  }, [catalog]);
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-sm">evidence scope</TableHead>
            <TableHead className="text-sm">metrics</TableHead>
            <TableHead className="text-sm">metric ids</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {byScope.map(([scope, ids]) => (
            <TableRow key={scope}>
              <TableCell className="align-top text-sm">{scope}</TableCell>
              <TableCell className="align-top text-sm">{ids.length}</TableCell>
              <TableCell className="text-muted-foreground align-top font-mono text-sm">
                {ids.join(", ")}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
