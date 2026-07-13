import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { loadDiagnosticCatalog } from "@/lib/diagnostics";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DiagnosticWiki } from "@/components/diagnostics/diagnostic-wiki";

export const dynamic = "force-dynamic";

export default async function DiagnosticsPage() {
  const catalog = await loadDiagnosticCatalog();
  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="border-border/60 shrink-0 border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-6 py-4">
          <Link href="/" className="text-muted-foreground hover:text-foreground" aria-label="Home">
            <ArrowLeft className="size-5" />
          </Link>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Diagnostic wiki</h1>
            <p className="text-muted-foreground text-sm">
              How to read this: a <strong className="text-foreground font-medium">metric</strong> feeds a{" "}
              <strong className="text-foreground font-medium">signal</strong>, signals point to an{" "}
              <strong className="text-foreground font-medium">issue</strong>, each issue has candidate{" "}
              <strong className="text-foreground font-medium">root causes</strong>, and every cause has a
              confirmatory <strong className="text-foreground font-medium">test</strong> and a{" "}
              <strong className="text-foreground font-medium">fix</strong>. Pick an issue family to explore.
            </p>
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl px-6 py-8">
          {!catalog || catalog.issues.length === 0 ? (
            <Card className="border-dashed">
              <CardHeader className="items-center py-14 text-center">
                <CardTitle className="text-base">No diagnostic catalog found</CardTitle>
                <CardDescription className="max-w-md">
                  Generate it with <code>python -m qc.catalog render</code>, which writes{" "}
                  <code>spec/diagnostics/catalog.json</code> from{" "}
                  <code>qc/catalog/diagnostic_catalog.yaml</code>.
                </CardDescription>
              </CardHeader>
            </Card>
          ) : (
            <DiagnosticWiki catalog={catalog} />
          )}
        </div>
      </div>
    </main>
  );
}
