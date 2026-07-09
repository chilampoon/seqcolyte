"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Sparkles, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { Streamdown } from "streamdown";
import type { Conclusion } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

export function ConclusionsPanel({
  projectId,
  reloadToken = 0,
}: {
  projectId: string;
  reloadToken?: number;
}) {
  const [items, setItems] = useState<Conclusion[]>([]);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`/api/projects/${projectId}/conclusions`, { cache: "no-store" });
    if (r.ok) setItems(((await r.json()) as { items: Conclusion[] }).items ?? []);
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load, reloadToken]);

  async function add() {
    if (!title.trim() && !body.trim()) return;
    setBusy(true);
    try {
      const r = await fetch(`/api/projects/${projectId}/conclusions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title, body, source: "manual" }),
      });
      if (r.ok) {
        setTitle("");
        setBody("");
        setAdding(false);
        toast.success("Conclusion added");
        await load();
      } else {
        toast.error("Could not add conclusion");
      }
    } finally {
      setBusy(false);
    }
  }

  async function del(cid: string) {
    await fetch(`/api/projects/${projectId}/conclusions/${cid}`, { method: "DELETE" });
    await load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-sm">
          Curated takeaways for this project — pin a diagnosis from Results or write your own.
        </p>
        {!adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus className="size-4" /> Add
          </Button>
        )}
      </div>

      {adding && (
        <Card>
          <CardContent className="space-y-2 py-4">
            <Input
              placeholder="Title (e.g. Adapter-dimer contamination confirmed)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <Textarea
              placeholder="What did you conclude? Markdown supported."
              rows={4}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
                <X className="size-4" /> Cancel
              </Button>
              <Button size="sm" onClick={add} disabled={busy || (!title.trim() && !body.trim())}>
                {busy ? "Saving…" : "Save conclusion"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {items.length === 0 && !adding ? (
        <Card className="border-dashed">
          <CardContent className="text-muted-foreground py-14 text-center text-sm">
            No conclusions yet. Pin the diagnosis from a run, or add your own.
          </CardContent>
        </Card>
      ) : (
        items.map((c) => (
          <Card key={c.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-sm">{c.title}</CardTitle>
                <div className="flex items-center gap-2">
                  {c.source === "diagnosis" && (
                    <Badge variant="secondary" className="gap-1 text-[10px]">
                      <Sparkles className="size-2.5" /> from AI diagnosis
                    </Badge>
                  )}
                  <button
                    onClick={() => del(c.id)}
                    className="text-muted-foreground hover:text-destructive"
                    title="Delete"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </div>
              <p className="text-muted-foreground text-[11px]">
                {new Date(c.createdAt).toLocaleString(undefined, {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
                {c.runId ? ` · run ${c.runId}` : ""}
              </p>
            </CardHeader>
            {c.body && (
              <CardContent className="pt-0 text-sm">
                <Streamdown>{c.body}</Streamdown>
              </CardContent>
            )}
          </Card>
        ))
      )}
    </div>
  );
}
