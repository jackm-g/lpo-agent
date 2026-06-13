import type { LpIr, SolverResult } from "../types";
import { analyzeDecision, type ProfileItem, type RiskLevel } from "../riskProfile";

interface Props {
  ir: LpIr;
  result: SolverResult;
}

export default function DecisionProfile({ ir, result }: Props) {
  const p = analyzeDecision(ir, result);

  return (
    <div className="profile">
      <div className={`risk-summary level-${p.level.toLowerCase()}`}>
        <span className="risk-chip">{p.level} risk</span>
        <span className="risk-headline">{p.headline}</span>
      </div>

      <div className="profile-cols">
        <Column kind="pros" title="Strengths" subtitle="why this plan holds up" items={p.pros} level={p.level} />
        <Column kind="cons" title="Risks" subtitle="where it's exposed" items={p.cons} level={p.level} />
      </div>

      {p.levers.length > 0 && (
        <div className="levers">
          <h4>
            <span className="lever-icon">▲</span> Where more capacity pays off
          </h4>
          <ul>
            {p.levers.map((l) => (
              <li key={l.name}>
                <span className="lever-mag">{l.magnitudeLabel}</span>
                <span className="lever-body">
                  <strong>{humanize(l.name)}</strong> — {l.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {p.caveats.length > 0 && (
        <ul className="profile-caveats">
          {p.caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Column({
  kind,
  title,
  subtitle,
  items,
  level,
}: {
  kind: "pros" | "cons";
  title: string;
  subtitle: string;
  items: ProfileItem[];
  level: RiskLevel;
}) {
  return (
    <section className={`profile-col ${kind}`}>
      <h4>
        <span className="profile-icon">{kind === "pros" ? "✓" : "!"}</span>
        {title} <span className="profile-sub">— {subtitle}</span>
      </h4>
      {items.length === 0 ? (
        <p className="profile-empty">
          {kind === "cons" ? "No binding limits — nothing is at zero buffer." : "—"}
        </p>
      ) : (
        <ul>
          {items.map((it) => (
            <li key={it.name}>
              <div className="profile-row-head">
                <strong>{it.name === "optimal" ? "Best achievable" : humanize(it.name)}</strong>
                {it.magnitudeLabel && (
                  <span className={`profile-mag ${kind}`}>{it.magnitudeLabel}</span>
                )}
              </div>
              <p className="profile-detail">{it.detail}</p>
              {it.sub && <p className="profile-prov">“{it.sub}”</p>}
            </li>
          ))}
        </ul>
      )}
      {kind === "cons" && level === "Elevated" && items.length > 0 && (
        <p className="knife-edge">⚠ Multiple limits bind at once — a small data error can change the recommendation.</p>
      )}
    </section>
  );
}

function humanize(name: string): string {
  return name.replace(/_/g, " ");
}
