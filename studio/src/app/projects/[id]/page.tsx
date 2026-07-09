import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { getProject, listRuns, projectExists } from "@/lib/store";
import { Badge } from "@/components/ui/badge";
import { Workspace } from "@/components/workspace";
import { ModeToggle } from "@/components/mode-toggle";
import { EditableTitle } from "@/components/editable-title";

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
    <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="border-border/60 flex shrink-0 items-center justify-between gap-3 border-b px-4 py-2">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/"
            className="text-muted-foreground hover:text-foreground shrink-0"
            title="All projects"
          >
            <ArrowLeft className="size-4" />
          </Link>
          <div className="min-w-0">
            <EditableTitle projectId={id} initialName={project.name} />
            <p className="text-muted-foreground truncate text-xs">{project.assay}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="secondary" className="font-mono text-xs">
            {project.specId}
          </Badge>
          <ModeToggle />
        </div>
      </header>

      <Workspace project={project} initialRuns={runs} className="min-h-0 flex-1" />
    </main>
  );
}
