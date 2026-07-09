"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

export function NotesEditor({ projectId }: { projectId: string }) {
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/projects/${projectId}/inputs/notes`)
      .then((r) => r.json())
      .then((d: { notes?: string }) => {
        if (!cancelled) {
          setNotes(d.notes ?? "");
          setSaved(d.notes ?? "");
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const dirty = notes !== saved;

  async function save() {
    setBusy(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/inputs/notes`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ notes }),
      });
      if (res.ok) {
        setSaved(notes);
        toast.success("Notes saved");
      } else {
        toast.error("Could not save notes");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <Textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        rows={6}
        placeholder="Sample prep notes, batch, operator, kit lot, anything the assistant should know about this run…"
        className="resize-y font-mono text-xs"
      />
      <div className="flex justify-end">
        <Button size="sm" variant={dirty ? "default" : "outline"} onClick={save} disabled={!dirty || busy}>
          {busy ? "Saving…" : dirty ? "Save notes" : "Saved"}
        </Button>
      </div>
    </div>
  );
}
