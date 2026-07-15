import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { listTechnologies } from "@/lib/technologies";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { TechGallery } from "@/components/tech-gallery";

export const dynamic = "force-dynamic";

export default async function TechnologiesPage() {
  const techs = await listTechnologies();
  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="border-border/60 shrink-0 border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-3 sm:px-6 sm:py-4">
          <Link href="/" className="text-muted-foreground hover:text-foreground shrink-0" aria-label="Home">
            <ArrowLeft className="size-5" />
          </Link>
          <div className="min-w-0">
            <h1 className="text-base font-semibold tracking-tight sm:text-lg">Technologies</h1>
            <p className="text-muted-foreground hidden text-sm sm:block">
              A collection of single-cell sequencing library structures.
            </p>
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
          {techs.length === 0 ? (
            <Card className="border-dashed">
              <CardHeader className="items-center py-14 text-center">
                <CardTitle className="text-base">No technologies yet</CardTitle>
                <CardDescription className="max-w-md">
                  Run <code>python -m extract wiki --tech &lt;folder&gt;</code> for each technology, then{" "}
                  <code>python -m extract wiki-index</code> to populate this gallery.
                </CardDescription>
              </CardHeader>
            </Card>
          ) : (
            <TechGallery techs={techs} />
          )}
        </div>
      </div>
    </main>
  );
}
