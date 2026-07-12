"use client";

import { SpecPanel } from "@/components/spec/spec-panel";

/** Mounts the shared SpecPanel against a technology's wiki spec endpoint. */
export function TechSpec({ id }: { id: string }) {
  return <SpecPanel specUrl={`/api/technologies/${id}/spec`} />;
}
