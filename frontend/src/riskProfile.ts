// Derive a decision-maker's pros/cons + risk profile from the solver output.
//
// Everything here is computed deterministically from the SolverResult — no LLM,
// no invented numbers (consistent with the project's "solver is the source of
// truth" rule). The mapping:
//   • binding constraint   -> a RISK: zero buffer; quantified downside if the
//                             resource comes up short (shadow_price × shortfall).
//   • slack constraint     -> a STRENGTH: head-room that makes the plan resilient.
//   • binding + shadowprice-> a LEVER: where adding capacity buys the most value.
import type { Constraint, LpIr, SolverResult } from "./types";

export interface ProfileItem {
  name: string; // constraint name
  sub: string; // the prompt span that produced it (provenance)
  detail: string; // plain-language pro/con/lever
  magnitude: number; // for ranking (objective-unit exposure, or buffer fraction)
  magnitudeLabel?: string; // short headline number, e.g. "−67.5" or "58% spare"
}

export type RiskLevel = "Low" | "Moderate" | "Elevated";

export interface DecisionProfile {
  objNoun: string; // "value" or "cost"
  level: RiskLevel;
  headline: string; // one-line risk summary
  pros: ProfileItem[];
  cons: ProfileItem[];
  levers: ProfileItem[];
  caveats: string[];
}

const SHORTFALL = 0.1; // model a 10% adverse change in a binding resource

export function analyzeDecision(ir: LpIr, result: SolverResult): DecisionProfile {
  const objNoun = ir.sense === "maximize" ? "value" : "cost";
  const srcByName = new Map<string, Constraint>(ir.constraints.map((c) => [c.name, c]));

  const pros: ProfileItem[] = [];
  const cons: ProfileItem[] = [];
  const levers: ProfileItem[] = [];

  for (const c of result.constraints) {
    const src = srcByName.get(c.name)?.source ?? "";
    const sp = c.shadow_price;

    if (c.binding) {
      const exposure = sp != null ? Math.abs(sp) * SHORTFALL * Math.abs(c.rhs) : 0;
      cons.push({
        name: c.name,
        sub: src,
        magnitude: exposure,
        magnitudeLabel: exposure ? `−${fmt(exposure)} ${objNoun}` : "no buffer",
        detail:
          `Fully consumed (${fmt(c.lhs_value)} / ${fmt(c.rhs)}) — zero buffer. ` +
          (sp != null && sp !== 0
            ? `If it comes up ~10% short, the plan loses ≈ ${fmt(exposure)} ${objNoun}.`
            : `Any shortfall here forces a worse plan.`),
      });
      if (sp != null && sp !== 0) {
        levers.push({
          name: c.name,
          sub: src,
          magnitude: exposure,
          magnitudeLabel: `+${fmt(exposure)} ${objNoun}`,
          detail: `Each extra unit is worth ≈ ${fmt(Math.abs(sp))} ${objNoun}; a 10% capacity bump adds ≈ ${fmt(exposure)} ${objNoun}.`,
        });
      }
    } else {
      const pct = c.rhs !== 0 ? c.slack / Math.abs(c.rhs) : 0;
      pros.push({
        name: c.name,
        sub: src,
        magnitude: pct,
        magnitudeLabel: pct ? `${Math.round(pct * 100)}% spare` : `${fmt(c.slack)} spare`,
        detail: `Only ${fmt(c.lhs_value)} of ${fmt(c.rhs)} used — ${fmt(c.slack)} to spare. The plan absorbs disruptions here without losing ${objNoun}.`,
      });
    }
  }

  // The achieved optimum is itself the headline strength.
  if (result.objective_value != null) {
    pros.unshift({
      name: "optimal",
      sub: "",
      magnitude: Number.POSITIVE_INFINITY,
      magnitudeLabel: fmt(result.objective_value),
      detail: `This is the best achievable ${objNoun} under every stated limit — no feasible plan does better.`,
    });
  }

  cons.sort((a, b) => b.magnitude - a.magnitude);
  levers.sort((a, b) => b.magnitude - a.magnitude);
  pros.sort((a, b) => b.magnitude - a.magnitude);

  const caveats: string[] = [];
  const usesRelaxation =
    result.is_integer_model &&
    result.constraints.some((c) => c.shadow_price_basis === "lp_relaxation");
  if (usesRelaxation) {
    caveats.push(
      "Downside/upside figures use LP-relaxation marginal values, so treat them as directional for this whole-unit (integer) plan, not exact.",
    );
  }
  caveats.push(
    "These risks assume the input numbers are accurate. The plan is only as good as the rates, limits, and weights you provided.",
  );

  const bindingCount = result.constraints.filter((c) => c.binding).length;
  const level: RiskLevel =
    bindingCount === 0 ? "Low" : bindingCount >= ir.variables.length ? "Elevated" : "Moderate";
  const headline =
    bindingCount === 0
      ? "Robust — every limit has spare capacity."
      : level === "Elevated"
        ? `Knife-edge — the plan sits where ${bindingCount} limits meet at once, so small errors in those inputs move the answer.`
        : `${bindingCount} resource${bindingCount === 1 ? " is" : "s are"} maxed out with no buffer.`;

  return { objNoun, level, headline, pros, cons, levers, caveats };
}

function fmt(n: number): string {
  if (!Number.isFinite(n)) return "—";
  if (Math.abs(n) >= 1000) return Math.round(n).toLocaleString();
  return Number.isInteger(n) ? n.toLocaleString() : Number(n.toFixed(2)).toString();
}
