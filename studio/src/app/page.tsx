import Link from "next/link";
import Image from "next/image";
import { runPreflight } from "@/lib/preflight";
import { listProjects, listRuns } from "@/lib/store";
import { PreflightPanel } from "@/components/preflight-panel";
import { NewProjectButton } from "@/components/new-project-button";
import { ModeToggle } from "@/components/mode-toggle";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ProjectManifest, Verdict } from "@/lib/types";

export const dynamic = "force-dynamic";

function DemoCard({ project, overall }: { project: ProjectManifest; overall: Verdict | null }) {
  const pass = overall === "pass";
  return (
    <Link href={`/projects/${project.id}`} className="group block">
      <Card
        className={cn(
          "h-full transition-colors",
          pass ? "group-hover:border-emerald-500/60" : "group-hover:border-red-500/60",
        )}
      >
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base leading-tight">{project.name}</CardTitle>
            {overall && (
              <span
                className={cn(
                  "shrink-0 rounded-md border px-2 py-0.5 text-xs font-semibold uppercase",
                  pass
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500"
                    : "border-red-500/40 bg-red-500/10 text-red-500",
                )}
              >
                {overall}
              </span>
            )}
          </div>
          <CardDescription className="line-clamp-2">{project.assay}</CardDescription>
          <p className="text-muted-foreground mt-1 text-xs">
            {project.demoBlurb ??
              (pass
                ? "Clean control — every QC check passes."
                : "Failures injected — QC catches them (recall 1.0).")}
          </p>
        </CardHeader>
      </Card>
    </Link>
  );
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function ProjectCard({ project }: { project: ProjectManifest }) {
  const runCount = project.runIds.length;
  return (
    <Link href={`/projects/${project.id}`} className="group block">
      <Card className="h-full transition-colors group-hover:border-primary/50">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base leading-tight">{project.name}</CardTitle>
            <Badge variant="secondary" className="shrink-0 font-mono text-[10px]">
              {project.specId}
            </Badge>
          </div>
          <CardDescription className="line-clamp-2">{project.assay}</CardDescription>
          <p className="text-muted-foreground mt-1 text-xs">
            {runCount === 0 ? "No runs yet" : `${runCount} run${runCount === 1 ? "" : "s"}`}
            {" · "}
            updated {fmtDate(project.updatedAt)}
          </p>
        </CardHeader>
      </Card>
    </Link>
  );
}

async function latestVerdict(projectId: string): Promise<Verdict | null> {
  try {
    const runs = await listRuns(projectId);
    return runs.find((r) => r.overall)?.overall ?? runs[0]?.overall ?? null;
  } catch {
    return null;
  }
}

export default async function Home() {
  const [preflight, projects] = await Promise.all([runPreflight(), listProjects()]);
  const demos = projects.filter((p) => p.demo);
  const rest = projects.filter((p) => !p.demo);
  const demoCards = await Promise.all(
    demos.map(async (p) => ({ project: p, overall: await latestVerdict(p.id) })),
  );
  // healthy (pass) first for a clean → problematic reading order
  demoCards.sort((a, b) => (a.overall === "pass" ? -1 : b.overall === "pass" ? 1 : 0));

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="border-border/60 shrink-0 border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="ring-border/60 relative size-9 shrink-0 overflow-hidden rounded-lg ring-1">
              <Image
                src="/seqcolyte-logo.png"
                alt="Seqcolyte"
                width={36}
                height={36}
                className="size-full object-cover"
                priority
              />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">Seqcolyte Studio</h1>
              <p className="text-muted-foreground text-sm">
                Protocol-aware sequencing QC — inputs, pipeline, results, and a grounded assistant.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Link
              href="/technologies"
              className="text-muted-foreground hover:text-foreground px-2 text-sm font-medium"
            >
              Technologies
            </Link>
            <ModeToggle />
            <NewProjectButton />
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid w-full max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[1fr_20rem]">
          <div className="space-y-8">
            {demoCards.length > 0 && (
              <section>
                <h2 className="text-foreground mb-1 text-sm font-semibold tracking-wide uppercase">
                  Demos
                </h2>
                <p className="text-muted-foreground mb-3 text-xs">
                  The same protocol-aware QC across modalities — Illumina short-read and Nanopore
                  long-read — each on a healthy vs. a problematic library. Open any to see the spec,
                  the run trace, and the report.
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  {demoCards.map(({ project, overall }) => (
                    <DemoCard key={project.id} project={project} overall={overall} />
                  ))}
                </div>
              </section>
            )}

            <section>
              <h2 className="text-muted-foreground mb-3 text-xs font-medium tracking-wide uppercase">
                Projects
              </h2>
              {rest.length === 0 ? (
                <Card className="border-dashed">
                  <CardHeader className="items-center py-14 text-center">
                    <CardTitle className="text-base">No projects yet</CardTitle>
                    <CardDescription className="max-w-sm">
                      Create a project to load a protocol, run the QC pipeline on your reads, and ask
                      the assistant about the results.
                    </CardDescription>
                    <div className="pt-3">
                      <NewProjectButton />
                    </div>
                  </CardHeader>
                </Card>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {rest.map((p) => (
                    <ProjectCard key={p.id} project={p} />
                  ))}
                </div>
              )}
            </section>
          </div>

        <aside>
          <h2 className="text-muted-foreground mb-3 text-xs font-medium uppercase tracking-wide">
            Setup
          </h2>
          <PreflightPanel preflight={preflight} />
        </aside>
        </div>
      </div>
    </main>
  );
}
