import type { SpecDataProcessing, DagNode } from "@/lib/types";

/**
 * Renders a data-processing pipeline as a DAG: stages are columns (left→right), nodes are boxes stacked
 * within their stage, and dependency edges are SVG connectors. Node order carries no meaning — the edges do.
 * Edge kinds are color-coded (sequential/branch/fan_in); per-cell vs bulk scope and viz-only terminals are
 * styled distinctly.
 */

const COLW = 190;
const ROWH = 64;
const NODEW = 168;
const NODEH = 48;
const PADX = 4;
const HEADER = 22;

const GUTTER = COLW - NODEW; // empty lane between two node columns

const EDGE_COLOR: Record<string, string> = {
  sequential: "var(--color-border)",
  branch: "#f59e0b",
  fan_in: "#0ea5e9",
};

/**
 * Orthogonal, gutter-routed connector from the right border of `a` to the left border of `b`, with
 * lightly rounded corners. Anchors sit on the box borders (never inside a box); vertical travel runs
 * in a column gutter rather than diagonally across the boxes between the two nodes. Any horizontal
 * segment that still grazes an intervening box is occluded by the opaque node layer drawn on top.
 */
function edgePath(a: { x: number; y: number }, b: { x: number; y: number }): string {
  const sx = a.x + NODEW; // exit at the source's right border
  const sy = a.y + NODEH / 2;
  const tx = b.x; // enter at the target's left border
  const ty = b.y + NODEH / 2;
  if (Math.abs(ty - sy) < 1) return `M ${sx} ${sy} L ${tx} ${ty}`; // same row → straight
  // vertical lane: in the gutter just before the target column for forward edges, just past the
  // source for same-column / backward edges — always a clear gutter, never over a box.
  const midx =
    tx - sx > GUTTER ? tx - GUTTER / 2 : tx > sx ? (sx + tx) / 2 : sx + GUTTER / 2;
  const v = ty > sy ? 1 : -1;
  const h1 = midx > sx ? 1 : -1;
  const h2 = tx > midx ? 1 : -1;
  const r = Math.min(
    6,
    Math.abs(ty - sy) / 2,
    Math.abs(midx - sx) || 6,
    Math.abs(tx - midx) || 6,
  );
  return [
    `M ${sx} ${sy}`,
    `L ${midx - h1 * r} ${sy}`,
    `Q ${midx} ${sy} ${midx} ${sy + v * r}`,
    `L ${midx} ${ty - v * r}`,
    `Q ${midx} ${ty} ${midx + h2 * r} ${ty}`,
    `L ${tx} ${ty}`,
  ].join(" ");
}

export function DataProcessingDag({ dp }: { dp: SpecDataProcessing }) {
  const nodes = dp.nodes ?? [];
  const edges = dp.edges ?? [];
  if (nodes.length === 0) return null;

  // stage ids in declared order, else discovered order
  const stageDefs = dp.stages ?? [];
  const declared = stageDefs.map((s) => s.id);
  const discovered = Array.from(new Set(nodes.map((n) => n.stage ?? "_")));
  const stageIds = declared.length ? declared : discovered;
  // any node whose stage isn't declared falls into a trailing "_" column
  for (const s of discovered) if (!stageIds.includes(s)) stageIds.push(s);
  const stageLabel = new Map(stageDefs.map((s) => [s.id, s.label]));

  const perStage = new Map<string, DagNode[]>();
  for (const id of stageIds) perStage.set(id, []);
  for (const n of nodes) perStage.get(n.stage && perStage.has(n.stage) ? n.stage : stageIds[stageIds.length - 1])!.push(n);

  const pos = new Map<string, { x: number; y: number }>();
  stageIds.forEach((sid, si) => {
    (perStage.get(sid) ?? []).forEach((n, ni) => pos.set(n.id, { x: si * COLW, y: HEADER + ni * ROWH }));
  });

  const maxRows = Math.max(1, ...stageIds.map((s) => perStage.get(s)?.length ?? 0));
  const width = Math.max(NODEW, (stageIds.length - 1) * COLW + NODEW) + PADX;
  const height = HEADER + maxRows * ROWH + 8;

  return (
    <div className="overflow-x-auto">
      <div className="relative" style={{ width, height }}>
        {/* edges */}
        <svg width={width} height={height} className="pointer-events-none absolute inset-0">
          {edges.map((e, i) => {
            const a = pos.get(e.from);
            const b = pos.get(e.to);
            if (!a || !b) return null;
            const c = EDGE_COLOR[e.kind ?? "sequential"] ?? EDGE_COLOR.sequential;
            return (
              <path
                key={i}
                d={edgePath(a, b)}
                fill="none"
                stroke={c}
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeDasharray={e.kind === "fan_in" ? "4 3" : undefined}
                opacity={0.8}
              />
            );
          })}
        </svg>
        {/* stage headers */}
        {stageIds.map((sid, si) =>
          stageLabel.get(sid) ? (
            <div
              key={`h-${sid}`}
              className="text-muted-foreground absolute truncate text-[10px] font-medium tracking-wide uppercase"
              style={{ left: si * COLW, top: 0, width: NODEW }}
            >
              {stageLabel.get(sid)}
            </div>
          ) : null,
        )}
        {/* nodes */}
        {nodes.map((n) => {
          const p = pos.get(n.id);
          if (!p) return null;
          return (
            <div
              key={n.id}
              className={[
                // opaque fills + z-10 so a node always occludes any edge routed behind it
                "absolute z-10 flex flex-col justify-center rounded-md border px-2 py-1 text-xs leading-tight",
                n.viz_only
                  ? "border-dashed border-border/60 bg-muted text-muted-foreground"
                  : n.scope === "per_cell"
                    ? "border-sky-500/50 bg-sky-50 dark:bg-sky-950"
                    : "border-border/70 bg-muted",
                n.terminal ? "ring-1 ring-primary/40" : "",
              ].join(" ")}
              style={{ left: p.x, top: p.y, width: NODEW, minHeight: NODEH }}
            >
              <span className="line-clamp-2 font-medium">{n.label}</span>
              {(n.tool || n.scope) && (
                <span className="text-muted-foreground mt-0.5 truncate text-[10px]">
                  {n.tool}
                  {n.tool && n.scope ? " · " : ""}
                  {n.scope === "per_cell" ? "per-cell" : n.scope === "bulk" ? "bulk" : ""}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
