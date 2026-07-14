import Link from "next/link";
import Image from "next/image";
import { runPreflight } from "@/lib/preflight";
import { listProjects } from "@/lib/store";
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
import type { ProjectManifest } from "@/lib/types";

export const dynamic = "force-dynamic";

function DemoCard({ project }: { project: ProjectManifest }) {
  const platform = /nanopore/i.test(project.assay) ? "Nanopore · long-read" : "Illumina · short-read";
  return (
    <Link href={`/projects/${project.id}`} className="group block">
      <Card className="group-hover:border-primary/50 h-full transition-colors">
        <CardHeader>
          <CardTitle className="text-base leading-tight">{project.name}</CardTitle>
          <div className="flex flex-wrap gap-1.5 pt-1">
            <Badge variant="secondary" className="text-[10px]">
              {platform}
            </Badge>
          </div>
          {project.demoBlurb && (
            <CardDescription className="line-clamp-3 pt-1">{project.demoBlurb}</CardDescription>
          )}
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

// curated example order: Nanopore starter (try it) → Illumina clean → Illumina problem
const EXAMPLE_ORDER = ["nanopore", "clean-library", "adapter-dimer"];
const exampleRank = (id: string) => {
  const i = EXAMPLE_ORDER.findIndex((k) => id.includes(k));
  return i < 0 ? 99 : i;
};

export default async function Home() {
  const [preflight, projects] = await Promise.all([runPreflight(), listProjects()]);
  const demos = projects.filter((p) => p.demo).sort((a, b) => exampleRank(a.id) - exampleRank(b.id));
  const rest = projects.filter((p) => !p.demo);

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
                Root cause analysis for genomic sequencing runs.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/diagnostics"
              className="border-border/70 bg-secondary/60 text-foreground hover:bg-secondary hover:border-border rounded-md border px-3 py-1.5 text-sm font-medium transition-colors"
            >
              Diagnostics
            </Link>
            <Link
              href="/technologies"
              className="border-border/70 bg-secondary/60 text-foreground hover:bg-secondary hover:border-border rounded-md border px-3 py-1.5 text-sm font-medium transition-colors"
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
            <section>
              <h2 className="text-foreground mb-3 text-sm font-semibold tracking-wide uppercase">
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

            {demos.length > 0 && (
              <section>
                <h2 className="text-foreground mb-1 text-sm font-semibold tracking-wide uppercase">
                  Examples
                </h2>
                <p className="text-muted-foreground mb-3 text-xs">
                  Worked cases across platforms — open any to see the extracted spec, the QC run, and the
                  diagnosis with its root cause and suggested fix.
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  {demos.map((project) => (
                    <DemoCard key={project.id} project={project} />
                  ))}
                </div>
              </section>
            )}
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
