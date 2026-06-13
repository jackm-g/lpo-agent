import type { LpIr, SolverResult } from "../types";
import DecisionProfile from "./DecisionProfile";

interface Props {
  ir: LpIr;
  result: SolverResult;
  explanation: string;
}

export default function ResultPanel({ ir, result, explanation }: Props) {
  const meaning = new Map(ir.variables.map((v) => [v.name, v.meaning]));
  const relaxation =
    result.is_integer_model &&
    result.constraints.some((c) => c.shadow_price_basis === "lp_relaxation");

  return (
    <div className="result">
      <div className="answer-card">
        <div className="answer-objective">
          <span className="answer-label">Optimal {ir.sense === "maximize" ? "value" : "cost"}</span>
          <span className="answer-value">{fmtNum(result.objective_value)}</span>
        </div>
        <ul className="decision-list">
          {Object.entries(result.variables).map(([name, val]) => (
            <li key={name}>
              <span className="decision-val">{fmtNum(val)}</span>
              <span className="decision-name">
                <code>{name}</code> {meaning.get(name) ?? ""}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <section className="ir-block">
        <h3>
          <span className="ir-kicker">Decision risk profile</span> the pros &amp; cons
        </h3>
        <DecisionProfile ir={ir} result={result} />
      </section>

      <section className="ir-block">
        <h3>
          <span className="ir-kicker">Bottlenecks &amp; shadow prices</span>
        </h3>
        <table className="sp-table">
          <thead>
            <tr>
              <th>Constraint</th>
              <th>Status</th>
              <th>Shadow price</th>
            </tr>
          </thead>
          <tbody>
            {result.constraints.map((c) => (
              <tr key={c.name}>
                <td>
                  <code>{c.name}</code>
                </td>
                <td>
                  <span className={`badge ${c.binding ? "binding" : "slack"}`}>
                    {c.binding ? "binding" : `slack ${fmtNum(c.slack)}`}
                  </span>
                </td>
                <td>
                  {c.shadow_price == null ? "—" : fmtNum(c.shadow_price)}
                  {c.shadow_price != null && c.shadow_price_basis === "lp_relaxation" && (
                    <span className="basis-tag" title="LP-relaxation directional indicator, not an exact integer marginal value">
                      ~rel
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {relaxation && (
          <p className="caveat">
            This is an integer model, so shadow prices come from the LP relaxation
            (<code>~rel</code>): directional indicators, not exact “value of one more unit”
            figures.
          </p>
        )}
      </section>

      <section className="ir-block">
        <h3>
          <span className="ir-kicker">Explanation</span> grounded in the solver numbers
        </h3>
        <p className="explanation">{explanation}</p>
      </section>
    </div>
  );
}

function fmtNum(n: number | null): string {
  if (n == null) return "—";
  if (!Number.isInteger(n)) return Number(n.toFixed(4)).toString();
  return n.toLocaleString();
}
