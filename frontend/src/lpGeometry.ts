// Geometry for plotting a 2-variable LP: feasible polygon (half-plane clipping),
// axis bounds, and per-constraint boundary segments clipped to the view box.
import type { LpIr, Term } from "./types";

export interface Pt {
  x: number;
  y: number;
}

export interface ConstraintLine {
  name: string;
  /** Endpoints of the boundary line clipped to the view box (null if off-view). */
  segment: [Pt, Pt] | null;
  binding?: boolean;
}

export interface Plottable {
  xVar: string;
  yVar: string;
  xLabel: string;
  yLabel: string;
  xMax: number;
  yMax: number;
  /** Feasible-region polygon vertices in data coordinates (CCW), possibly empty. */
  feasible: Pt[];
  lines: ConstraintLine[];
  objective: { cx: number; cy: number }; // objective coefficients on (xVar, yVar)
}

const EPS = 1e-9;

export function coefOf(terms: Term[], name: string): number {
  return terms.filter((t) => t.var === name).reduce((s, t) => s + t.coef, 0);
}

/** Returns a Plottable when the IR has exactly two variables, else null. */
export function toPlottable(ir: LpIr): Plottable | null {
  if (ir.variables.length !== 2) return null;
  const [vx, vy] = ir.variables;
  const xVar = vx.name;
  const yVar = vy.name;

  const xMax = axisMax(ir, xVar, vx.upper ?? null);
  const yMax = axisMax(ir, yVar, vy.upper ?? null);

  // Start from the variable-bound box, then clip by every constraint half-plane.
  const xLo = vx.lower ?? 0;
  const yLo = vy.lower ?? 0;
  let poly: Pt[] = [
    { x: xLo, y: yLo },
    { x: xMax, y: yLo },
    { x: xMax, y: yMax },
    { x: xLo, y: yMax },
  ];
  // Respect finite upper bounds as extra half-planes.
  if (vx.upper != null) poly = clip(poly, 1, 0, vx.upper);
  if (vy.upper != null) poly = clip(poly, 0, 1, vy.upper);

  for (const c of ir.constraints) {
    const a = coefOf(c.terms, xVar);
    const b = coefOf(c.terms, yVar);
    if (Math.abs(a) < EPS && Math.abs(b) < EPS) continue;
    if (c.op === "<=") poly = clip(poly, a, b, c.rhs);
    else if (c.op === ">=") poly = clip(poly, -a, -b, -c.rhs);
    else {
      poly = clip(poly, a, b, c.rhs);
      poly = clip(poly, -a, -b, -c.rhs);
    }
  }

  const lines: ConstraintLine[] = ir.constraints.map((c) => ({
    name: c.name,
    segment: boundarySegment(coefOf(c.terms, xVar), coefOf(c.terms, yVar), c.rhs, xMax, yMax),
  }));

  return {
    xVar,
    yVar,
    xLabel: vx.meaning || xVar,
    yLabel: vy.meaning || yVar,
    xMax,
    yMax,
    feasible: poly,
    lines,
    objective: { cx: coefOf(ir.objective, xVar), cy: coefOf(ir.objective, yVar) },
  };
}

/** Sutherland–Hodgman clip of a convex polygon by the half-plane a·x + b·y ≤ c. */
function clip(poly: Pt[], a: number, b: number, c: number): Pt[] {
  if (poly.length === 0) return poly;
  const inside = (p: Pt) => a * p.x + b * p.y <= c + 1e-7;
  const out: Pt[] = [];
  for (let i = 0; i < poly.length; i++) {
    const cur = poly[i];
    const prev = poly[(i + poly.length - 1) % poly.length];
    const curIn = inside(cur);
    const prevIn = inside(prev);
    if (curIn) {
      if (!prevIn) out.push(intersect(prev, cur, a, b, c));
      out.push(cur);
    } else if (prevIn) {
      out.push(intersect(prev, cur, a, b, c));
    }
  }
  return out;
}

function intersect(p1: Pt, p2: Pt, a: number, b: number, c: number): Pt {
  const d1 = a * p1.x + b * p1.y - c;
  const d2 = a * p2.x + b * p2.y - c;
  const t = d1 / (d1 - d2);
  return { x: p1.x + t * (p2.x - p1.x), y: p1.y + t * (p2.y - p1.y) };
}

/** Boundary line a·x + b·y = c, clipped to the [0,xMax]×[0,yMax] box. */
export function boundarySegment(a: number, b: number, c: number, xMax: number, yMax: number): [Pt, Pt] | null {
  const pts: Pt[] = [];
  const push = (x: number, y: number) => {
    if (x >= -EPS && x <= xMax + EPS && y >= -EPS && y <= yMax + EPS) pts.push({ x, y });
  };
  if (Math.abs(b) > EPS) {
    push(0, c / b);
    push(xMax, (c - a * xMax) / b);
  }
  if (Math.abs(a) > EPS) {
    push(c / a, 0);
    push((c - b * yMax) / a, yMax);
  }
  // Dedup and pick the two extreme points.
  const uniq = pts.filter(
    (p, i) => pts.findIndex((q) => Math.abs(q.x - p.x) < 1e-6 && Math.abs(q.y - p.y) < 1e-6) === i,
  );
  if (uniq.length < 2) return null;
  return [uniq[0], uniq[uniq.length - 1]];
}

/** A sensible upper bound for an axis: a margin past the tightest intercepts/bound. */
function axisMax(ir: LpIr, varName: string, upper: number | null): number {
  const candidates: number[] = [];
  if (upper != null) candidates.push(upper);
  for (const c of ir.constraints) {
    const a = coefOf(c.terms, varName);
    if (Math.abs(a) > EPS && c.rhs / a > 0) candidates.push(c.rhs / a);
  }
  const m = candidates.length ? Math.max(...candidates) : 10;
  return roundUpNice(m * 1.15);
}

function roundUpNice(v: number): number {
  if (v <= 0) return 10;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  return Math.ceil(v / mag) * mag;
}

/** Integer-feasible lattice points inside the polygon (for small models only). */
export function latticePoints(p: Plottable, ir: LpIr, cap = 1200): Pt[] {
  const intX = ir.variables[0].integer;
  const intY = ir.variables[1].integer;
  if (!intX && !intY) return [];
  const stepX = intX ? 1 : Math.max(p.xMax / 40, 1);
  const stepY = intY ? 1 : Math.max(p.yMax / 40, 1);
  const pts: Pt[] = [];
  for (let x = 0; x <= p.xMax + EPS; x += stepX) {
    for (let y = 0; y <= p.yMax + EPS; y += stepY) {
      if (feasibleAt(ir, p, x, y)) {
        pts.push({ x, y });
        if (pts.length > cap) return pts;
      }
    }
  }
  return pts;
}

function feasibleAt(ir: LpIr, p: Plottable, x: number, y: number): boolean {
  for (const c of ir.constraints) {
    const a = coefOf(c.terms, p.xVar);
    const b = coefOf(c.terms, p.yVar);
    const lhs = a * x + b * y;
    if (c.op === "<=" && lhs > c.rhs + 1e-6) return false;
    if (c.op === ">=" && lhs < c.rhs - 1e-6) return false;
    if (c.op === "==" && Math.abs(lhs - c.rhs) > 1e-6) return false;
  }
  return true;
}
