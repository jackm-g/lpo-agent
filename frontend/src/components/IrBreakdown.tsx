import type { Constraint, LpIr, SolverResult, Term } from "../types";

const OP_TEXT: Record<string, string> = { "<=": "≤", ">=": "≥", "==": "=" };

function expr(terms: Term[]): string {
  return terms
    .map((t, i) => {
      const c = t.coef;
      const sign = i === 0 ? (c < 0 ? "−" : "") : c < 0 ? " − " : " + ";
      const mag = Math.abs(c);
      const coef = mag === 1 ? "" : `${fmtNum(mag)}·`;
      return `${sign}${coef}${t.var}`;
    })
    .join("");
}

function fmtNum(n: number): string {
  return Number.isInteger(n) ? String(n) : String(n);
}

interface Props {
  ir: LpIr;
  result?: SolverResult | null;
}

export default function IrBreakdown({ ir, result }: Props) {
  const senseWord = ir.sense === "maximize" ? "Maximize" : "Minimize";
  const resByName = new Map((result?.constraints ?? []).map((c) => [c.name, c]));

  return (
    <div className="ir">
      <section className="ir-block">
        <h3>
          <span className="ir-kicker">Objective</span> what we're optimizing
        </h3>
        <p className="formula objective-formula">
          <span className="sense">{senseWord}</span> {expr(ir.objective)}
        </p>
      </section>

      <section className="ir-block">
        <h3>
          <span className="ir-kicker">Decision variables</span> the knobs
        </h3>
        <ul className="var-list">
          {ir.variables.map((v) => (
            <li key={v.name}>
              <code>{v.name}</code>
              <span className="var-meaning">{v.meaning}</span>
              <span className="badge subtle">{v.integer ? "integer" : "continuous"}</span>
              <span className="badge subtle">{bounds(v.lower, v.upper)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="ir-block">
        <h3>
          <span className="ir-kicker">Constraints</span> the limits — each traced to your words
        </h3>
        <ul className="con-list">
          {ir.constraints.map((c) => (
            <ConstraintRow key={c.name} c={c} res={resByName.get(c.name)} />
          ))}
          {ir.constraints.length === 0 && <li className="muted">No explicit constraints.</li>}
        </ul>
      </section>
    </div>
  );
}

function ConstraintRow({
  c,
  res,
}: {
  c: Constraint;
  res?: SolverResult["constraints"][number];
}) {
  return (
    <li className="con-row">
      <div className="con-formula">
        <strong>{c.name}</strong>
        <span className="formula">
          {expr(c.terms)} {OP_TEXT[c.op]} {fmtNum(c.rhs)}
        </span>
        {res && (
          <span className={`badge ${res.binding ? "binding" : "slack"}`}>
            {res.binding ? "binding" : `slack ${fmtNum(res.slack)}`}
          </span>
        )}
      </div>
      <div className="provenance">
        <span className="prov-arrow">↳ from your prompt:</span> “{c.source}”
      </div>
    </li>
  );
}

function bounds(lower: number | null, upper?: number | null): string {
  if (lower == null && upper == null) return "unbounded";
  if (lower != null && (upper == null || upper === undefined)) return `≥ ${lower}`;
  if (lower == null && upper != null) return `≤ ${upper}`;
  return `[${lower}, ${upper}]`;
}
