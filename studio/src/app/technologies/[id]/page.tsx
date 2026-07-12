import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { TechSpec } from "@/components/spec/tech-spec";

export const dynamic = "force-dynamic";

export default async function TechnologyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="border-border/60 shrink-0 border-b">
        <div className="mx-auto flex w-full max-w-4xl items-center gap-3 px-6 py-4">
          <Link
            href="/technologies"
            className="text-muted-foreground hover:text-foreground"
            aria-label="Back to technologies"
          >
            <ArrowLeft className="size-5" />
          </Link>
          <h1 className="text-base font-semibold tracking-tight">Technology spec</h1>
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-4xl px-6 py-8">
          <TechSpec id={id} />
        </div>
      </div>
    </main>
  );
}
