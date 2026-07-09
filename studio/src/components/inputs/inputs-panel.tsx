import { Database, Dna, FileText, StickyNote } from "lucide-react";
import type { ProjectManifest } from "@/lib/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { NotesEditor } from "./notes-editor";

function InputCard({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof FileText;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon className="text-muted-foreground size-4" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm">{children}</CardContent>
    </Card>
  );
}

export function InputsPanel({ project }: { project: ProjectManifest }) {
  return (
    <div className="space-y-4">
      <InputCard icon={StickyNote} title="Lab notes">
        <p className="text-muted-foreground mb-2 text-xs">
          Free-text context for this run — the assistant reads these to ground its answers.
        </p>
        <NotesEditor projectId={project.id} />
      </InputCard>

      <div className="grid gap-4 sm:grid-cols-2">
        <InputCard icon={FileText} title="Protocol document">
          {project.inputs.protocolDoc ? (
            <span className="font-mono text-xs">{project.inputs.protocolDoc}</span>
          ) : (
            <CardDescription>
              No protocol uploaded — QC uses the reference{" "}
              <Badge variant="secondary" className="font-mono text-[10px]">
                {project.specId}
              </Badge>{" "}
              spec. Uploading a PDF to extract a project-specific spec is a planned next step.
            </CardDescription>
          )}
        </InputCard>

        <InputCard icon={Database} title="Reads">
          <CardDescription>
            Choose a dataset when you run the pipeline: the labeled adapter-dimer simulation (for
            scored QC) or the clean 10x PBMC control.
          </CardDescription>
        </InputCard>

        <InputCard icon={Dna} title="Expected structure (spec)">
          <CardDescription>
            {project.assay}. The spec drives every check and the evidence chain — see the{" "}
            <span className="font-medium">Spec</span> tab for oligos, read structure, and the
            wet-lab build steps.
          </CardDescription>
        </InputCard>
      </div>
    </div>
  );
}
