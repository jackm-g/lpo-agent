import { useMemo } from "react";
import type { LpIr, SolverResult } from "../types";
import { boundarySegment, latticePoints, toPlottable, type Pt } from "../lpGeometry";

const W = 720;
const H = 560;
const PAD = { l: 56, r: 24, t: 24, b: 52 };

const LINE_COLORS = ["#2e6fb0", "#e08e0b", "#7b4fa3", "#16a085", "#d35400", "#2c3e50"];

interface Props {
  ir: LpIr;
  result?: SolverResult | null;
}

export default function LpGraph({ ir, result }: Props) {
  const plot = useMemo(() => toPlottable(ir), [ir]);

  if (!plot) {
    return (
      <div className="graph-fallback">
        <p>
          The feasible-region graph is drawn for <strong>two-variable</strong> models. This
          model has <strong>{ir.variables.length}</strong> variable
          {ir.variables.length === 1 ? "" : "s"} ({ir.variables.map((v) => v.name).join(", ")}),
          so it lives in {ir.variables.length}-D space and can't be shown as a 2-D plot. The
          solver still solves it exactly — see the answer panel.
        </p>
      </div>
    );
  }

  const sx = (x: number) => PAD.l + (x / plot.xMax) * (W - PAD.l - PAD.r);
  const sy = (y: number) => H - PAD.b - (y / plot.yMax) * (H - PAD.t - PAD.b);
  const sp = (p: Pt) => `${sx(p.x)},${sy(p.y)}`;

  const bindingByName = new Map(
    (result?.constraints ?? []).map((c) => [c.name, c.binding]),
  );

  const opt =
    result && result.status === "optimal"
      ? { x: result.variables[plot.xVar] ?? 0, y: result.variables[plot.yVar] ?? 0 }
      : null;

  // Objective iso-value contour through the optimum.
  const objSeg =
    opt && (plot.objective.cx !== 0 || plot.objective.cy !== 0)
      ? boundarySegment(
          plot.objective.cx,
          plot.objective.cy,
          plot.objective.cx * opt.x + plot.objective.cy * opt.y,
          plot.xMax,
          plot.yMax,
        )
      : null;

  const lattice = useMemo(() => latticePoints(plot, ir), [plot, ir]);

  const xTicks = ticks(plot.xMax);
  const yTicks = ticks(plot.yMax);

  return (
    <svg
      className="lp-graph"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Feasible region and optimum of the linear program"
    >
      {/* axes */}
      <line x1={PAD.l} y1={sy(0)} x2={W - PAD.r} y2={sy(0)} className="axis" />
      <line x1={sx(0)} y1={PAD.t} x2={sx(0)} y2={H - PAD.b} className="axis" />

      {/* grid + ticks */}
      {xTicks.map((t) => (
        <g key={`xt${t}`}>
          <line x1={sx(t)} y1={PAD.t} x2={sx(t)} y2={H - PAD.b} className="grid" />
          <text x={sx(t)} y={H - PAD.b + 18} className="tick">
            {fmt(t)}
          </text>
        </g>
      ))}
      {yTicks.map((t) => (
        <g key={`yt${t}`}>
          <line x1={PAD.l} y1={sy(t)} x2={W - PAD.r} y2={sy(t)} className="grid" />
          <text x={PAD.l - 8} y={sy(t) + 4} className="tick tick-y">
            {fmt(t)}
          </text>
        </g>
      ))}

      {/* feasible region */}
      {plot.feasible.length >= 3 && (
        <polygon points={plot.feasible.map(sp).join(" ")} className="feasible" />
      )}

      {/* integer lattice */}
      {lattice.length > 0 &&
        lattice.length <= 900 &&
        lattice.map((p, i) => (
          <circle key={`l${i}`} cx={sx(p.x)} cy={sy(p.y)} r={2} className="lattice" />
        ))}

      {/* constraint boundary lines */}
      {plot.lines.map((ln, i) =>
        ln.segment ? (
          <g key={ln.name}>
            <line
              x1={sx(ln.segment[0].x)}
              y1={sy(ln.segment[0].y)}
              x2={sx(ln.segment[1].x)}
              y2={sy(ln.segment[1].y)}
              stroke={LINE_COLORS[i % LINE_COLORS.length]}
              strokeWidth={bindingByName.get(ln.name) ? 4 : 2}
              strokeDasharray={bindingByName.get(ln.name) ? undefined : "1 0"}
            />
          </g>
        ) : null,
      )}

      {/* objective contour through optimum */}
      {objSeg && (
        <line
          x1={sx(objSeg[0].x)}
          y1={sy(objSeg[0].y)}
          x2={sx(objSeg[1].x)}
          y2={sy(objSeg[1].y)}
          className="objective"
        />
      )}

      {/* optimum marker */}
      {opt && (
        <g>
          <circle cx={sx(opt.x)} cy={sy(opt.y)} r={7} className="optimum" />
          <text x={sx(opt.x)} y={sy(opt.y) - 12} className="optimum-label">
            ({fmt(opt.x)}, {fmt(opt.y)})
          </text>
        </g>
      )}

      {/* axis labels */}
      <text x={(W + PAD.l) / 2} y={H - 8} className="axis-label">
        {plot.xVar} — {truncate(plot.xLabel)}
      </text>
      <text
        x={-(H - PAD.b + PAD.t) / 2}
        y={16}
        className="axis-label"
        transform="rotate(-90)"
      >
        {plot.yVar} — {truncate(plot.yLabel)}
      </text>
    </svg>
  );
}

function ticks(max: number): number[] {
  const step = niceStep(max);
  const out: number[] = [];
  for (let t = 0; t <= max + 1e-9; t += step) out.push(Number(t.toFixed(6)));
  return out;
}
function niceStep(max: number): number {
  const raw = max / 6;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  const m = n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10;
  return m * mag;
}
function fmt(v: number): string {
  if (Math.abs(v) >= 1000) return `${Math.round(v / 1000)}k`;
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}
function truncate(s: string, n = 22): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}
