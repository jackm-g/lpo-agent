import { useState } from "react";
import * as liveApi from "./api";
import { demoApi } from "./api";
import { DEMO_PROMPT } from "./demoData";
import IrBreakdown from "./components/IrBreakdown";
import LpGraph from "./components/LpGraph";
import ResultPanel from "./components/ResultPanel";
import { isSuccess, type LpIr, type SolverResult } from "./types";

type Phase = "edit" | "formulating" | "review" | "solving" | "done" | "info";
type Mode = "demo" | "live";

const STEPS = ["Describe", "Review elements", "Solution"] as const;

export default function App() {
  const [mode, setMode] = useState<Mode>("demo");
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState("");
  const [phase, setPhase] = useState<Phase>("edit");
  const [ir, setIr] = useState<LpIr | null>(null);
  const [restatement, setRestatement] = useState("");
  const [result, setResult] = useState<SolverResult | null>(null);
  const [explanation, setExplanation] = useState("");
  const [traceId, setTraceId] = useState("");
  const [info, setInfo] = useState("");
  const [error, setError] = useState("");

  const client = mode === "demo" ? demoApi : liveApi;
  const stepIndex = phase === "edit" || phase === "formulating" || phase === "info" ? 0
    : phase === "review" || phase === "solving" ? 1 : 2;

  async function handleFormulate() {
    if (!prompt.trim()) return;
    setError("");
    setInfo("");
    setResult(null);
    setExplanation("");
    setPhase("formulating");
    try {
      const r = await client.solve({
        question: prompt,
        context,
        requireConfirmation: true,
      });
      setTraceId(r.trace_id);
      if (r.status === "need_confirmation" && r.ir) {
        setIr(r.ir);
        setRestatement(r.restatement ?? "");
        setPhase("review");
      } else if (r.status === "need_info" || r.status === "escalated") {
        setInfo(r.status === "need_info" ? r.message : `Could not converge: ${r.message}`);
        setPhase("info");
      } else if (isSuccess(r)) {
        applySuccess(r.ir, r.result, r.explanation, r.restatement);
      }
    } catch (e) {
      setError(describeError(e));
      setPhase("edit");
    }
  }

  async function handleSolve(approved: boolean) {
    if (!approved) {
      setPhase("edit");
      return;
    }
    setError("");
    setPhase("solving");
    try {
      const r = await client.confirm(traceId, true);
      if (isSuccess(r)) {
        applySuccess(r.ir, r.result, r.explanation, r.restatement);
      } else if (r.status === "need_confirmation" && r.ir) {
        // Recovery loop reformulated; review the revised model.
        setIr(r.ir);
        setRestatement(r.restatement ?? "");
        setPhase("review");
      } else {
        setInfo(r.message);
        setPhase("info");
      }
    } catch (e) {
      setError(describeError(e));
      setPhase("review");
    }
  }

  function applySuccess(newIr: LpIr, res: SolverResult, expl: string, rest: string) {
    setIr(newIr);
    setResult(res);
    setExplanation(expl);
    setRestatement(rest);
    setPhase("done");
  }

  function reset() {
    setPhase("edit");
    setResult(null);
    setExplanation("");
    setInfo("");
    setError("");
  }

  const busy = phase === "formulating" || phase === "solving";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◆</span>
          <div>
            <h1>LPO Agent</h1>
            <p className="tagline">See how your words shape the optimization — then solve it.</p>
          </div>
        </div>
        <div className="mode-toggle" role="group" aria-label="Data source">
          <button
            className={mode === "demo" ? "on" : ""}
            onClick={() => setMode("demo")}
            disabled={busy}
          >
            Demo
          </button>
          <button
            className={mode === "live" ? "on" : ""}
            onClick={() => setMode("live")}
            disabled={busy}
            title="Calls the FastAPI backend at /api (start uvicorn lpo.api:app)"
          >
            Live API
          </button>
        </div>
      </header>

      <ol className="stepper">
        {STEPS.map((s, i) => (
          <li key={s} className={i === stepIndex ? "active" : i < stepIndex ? "complete" : ""}>
            <span className="step-no">{i + 1}</span>
            <span className="step-label">{s}</span>
          </li>
        ))}
      </ol>

      {error && <div className="banner error">{error}</div>}

      {/* Step 1 — prompt */}
      {(phase === "edit" || phase === "formulating" || phase === "info") && (
        <section className="card">
          <label className="field-label" htmlFor="prompt">
            Your decision question
          </label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. We can do scheduled services (worth 30) and field repairs (worth 75). A service is 20 mech-hours, a repair 40; we have 800 hours…"
            rows={7}
            disabled={busy}
          />
          <details className="context-details">
            <summary>Add structured context (optional)</summary>
            <textarea
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Known parameters / limits the model should assume."
              rows={3}
              disabled={busy}
            />
          </details>

          <div className="row">
            <button className="primary" onClick={handleFormulate} disabled={busy || !prompt.trim()}>
              {phase === "formulating" ? "Formulating…" : "Formulate ▸"}
            </button>
            <button className="link" onClick={() => setPrompt(DEMO_PROMPT)} disabled={busy}>
              Load example
            </button>
          </div>

          {phase === "info" && (
            <div className="banner info">
              <strong>The agent needs more information.</strong>
              <p>{info}</p>
              <p className="muted">
                It refused to invent the missing number — answer it in the prompt and formulate
                again.
              </p>
            </div>
          )}
        </section>
      )}

      {/* Step 2 — review the elements your prompt produced */}
      {(phase === "review" || phase === "solving") && ir && (
        <section className="card">
          <div className="card-head">
            <h2>How your prompt became a model</h2>
            <p className="muted">
              Every limit is traced back to your words. Check the inequalities and the objective
              before solving — a flipped sign is easy to catch here.
            </p>
          </div>
          <IrBreakdown ir={ir} />
          {restatement && (
            <details className="restatement">
              <summary>Plain-language restatement</summary>
              <pre>{restatement}</pre>
            </details>
          )}
          <div className="row">
            <button className="primary" onClick={() => handleSolve(true)} disabled={busy}>
              {phase === "solving" ? "Solving…" : "Looks right — solve it ▸"}
            </button>
            <button className="link" onClick={() => handleSolve(false)} disabled={busy}>
              ← Edit prompt
            </button>
          </div>
        </section>
      )}

      {/* Step 3 — graph + answer */}
      {phase === "done" && ir && result && (
        <>
          <section className="card">
            <div className="card-head">
              <h2>The optimization, solved</h2>
              <p className="muted">
                Feasible region (shaded), each resource limit (a line), and the optimum (●).
              </p>
            </div>
            <LpGraph ir={ir} result={result} />
            <Legend ir={ir} />
          </section>
          <section className="card">
            <ResultPanel ir={ir} result={result} explanation={explanation} />
            <div className="row">
              <button className="link" onClick={() => setPhase("review")}>
                ← Back to elements
              </button>
              <button className="link" onClick={reset}>
                Start over
              </button>
            </div>
            {traceId && <p className="trace">trace_id: {traceId}</p>}
          </section>
        </>
      )}

      <footer className="footer">
        <span>
          {mode === "demo"
            ? "Demo mode — Bradley motor-pool example, no backend needed."
            : "Live mode — POST /api/v1/solve → /api/v1/confirm."}
        </span>
      </footer>
    </div>
  );
}

function Legend({ ir }: { ir: LpIr }) {
  if (ir.variables.length !== 2) return null;
  return (
    <ul className="legend">
      <li>
        <span className="sw feasible-sw" /> feasible region
      </li>
      <li>
        <span className="sw line-sw" /> constraint (thick = binding)
      </li>
      <li>
        <span className="sw obj-sw" /> objective contour
      </li>
      <li>
        <span className="sw opt-sw" /> optimum
      </li>
    </ul>
  );
}

function describeError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  if (/Failed to fetch|NetworkError|ECONNREFUSED/i.test(msg)) {
    return "Couldn't reach the backend. Start it with `uvicorn lpo.api:app`, or switch to Demo mode.";
  }
  return msg;
}
