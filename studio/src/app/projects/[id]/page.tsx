import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { getProject, listRuns, projectExists } from "@/lib/store";
import { Badge } from "@/components/ui/badge";
import { Workspace } from "@/components/workspace";
import { ModeToggle } from "@/components/mode-toggle";

export const dynamic = "force-dynamic";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!(await projectExists(id))) notFound();
  const [project, runs] = await Promise.all([getProject(id), listRuns(id)]);

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
      <Link
        href="/"
        className="text-muted-foreground hover:text-foreground mb-4 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" />
        All projects
      </Link>

      <header className="mb-6 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{project.name}</h1>
          <p className="text-muted-foreground text-sm">{project.assay}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="font-mono text-xs">
            {project.specId}
          </Badge>
          <ModeToggle />
        </div>
      </header>

      <Workspace project={project} initialRuns={runs} />
    </main>
  );
}
