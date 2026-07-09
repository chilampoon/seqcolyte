"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

/** Nameless creation: one click → POST /api/projects → open the new project. */
export function NewProjectButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function create() {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "{}",
      });
      if (!res.ok) {
        toast.error("Could not create project");
        return;
      }
      const project = (await res.json()) as { id: string };
      router.push(`/projects/${project.id}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button size="sm" onClick={create} disabled={busy}>
      {busy ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
      New project
    </Button>
  );
}
