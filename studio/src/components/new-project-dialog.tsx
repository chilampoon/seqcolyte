"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function NewProjectDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) {
        const { error } = await res.json().catch(() => ({ error: "unknown error" }));
        toast.error(`Could not create project: ${error}`);
        return;
      }
      const project = (await res.json()) as { id: string };
      setOpen(false);
      setName("");
      router.push(`/projects/${project.id}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="size-4" />
          New project
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>New project</DialogTitle>
            <DialogDescription>
              A project holds your protocol, notes, pipeline runs, results, and a grounded
              assistant — all in one workspace.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2 py-4">
            <Label htmlFor="project-name">Project name</Label>
            <Input
              id="project-name"
              autoFocus
              placeholder="e.g. 10x PBMC re-prep — Aug batch"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!name.trim() || busy}>
              {busy ? "Creating…" : "Create project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
