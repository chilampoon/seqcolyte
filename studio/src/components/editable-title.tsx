"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Pencil } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/** Inline-editable project title. PATCHes name only; the id never changes. */
export function EditableTitle({
  projectId,
  initialName,
  className,
}: {
  projectId: string;
  initialName: string;
  className?: string;
}) {
  const router = useRouter();
  const [name, setName] = useState(initialName);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(initialName);
  const inputRef = useRef<HTMLInputElement>(null);
  const lastInitial = useRef(initialName);

  // Reflect a genuine server-side name change (e.g. auto-name after extraction) — but NOT on every
  // editing toggle, which used to clobber a just-saved optimistic name back to the stale prop.
  useEffect(() => {
    if (initialName !== lastInitial.current) {
      lastInitial.current = initialName;
      if (!editing) {
        setName(initialName);
        setDraft(initialName);
      }
    }
  }, [initialName, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  async function save() {
    const next = draft.trim();
    setEditing(false);
    if (!next || next === name) {
      setDraft(name);
      return;
    }
    const prev = name;
    setName(next);
    const res = await fetch(`/api/projects/${projectId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: next }),
    });
    if (!res.ok) {
      setName(prev);
      setDraft(prev);
      toast.error("Rename failed");
      return;
    }
    lastInitial.current = next; // keep the sync-guard in step with the saved name
    router.refresh(); // update the landing card + any other consumers of this name
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") {
            setDraft(name);
            setEditing(false);
          }
        }}
        className={cn(
          "border-input bg-background w-full max-w-md rounded-md border px-2 py-0.5 text-base font-semibold outline-none focus-visible:ring-1",
          className,
        )}
      />
    );
  }

  return (
    <button
      onClick={() => {
        setDraft(name);
        setEditing(true);
      }}
      className={cn(
        "group flex max-w-full items-center gap-1.5 truncate text-base font-semibold tracking-tight",
        className,
      )}
      title="Click to rename"
    >
      <span className="truncate">{name}</span>
      <Pencil className="text-muted-foreground size-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  );
}
