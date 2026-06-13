# LPO Agent — Frontend

A mobile-friendly React + TypeScript (Vite) UI for the LPO Agent. It's built
around one idea: **let the user see how their wording shapes the optimization
before it's solved.**

The flow mirrors the backend's two-call confirmation API:

1. **Describe** — type a decision question in plain language.
2. **Review elements** — the agent formulates it, and the UI shows the resulting
   LP *elements*: the objective, the decision variables, and every constraint —
   **each traced back to the words in your prompt** (provenance). Tweak the
   prompt and re-formulate to watch the elements change. If a number is missing,
   the agent asks instead of guessing (`need_info`).
3. **Solution** — approve the model and it's solved with HiGHS. For
   two-variable problems the UI draws the **LP graph** (feasible region,
   constraint lines, objective contour, and the optimum ●), then shows the
   decision, the binding constraints, shadow prices (with the integer caveat),
   and a grounded explanation.

## Run

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

It starts in **Demo mode** — the full Bradley motor-pool example runs entirely in
the browser with no backend or API key. Click **Load example** to drop in the
slang prompt, or type your own.

### Live mode (real LLM + solver)

Start the backend, then flip the toggle to **Live API**:

```bash
# from the repo root
uvicorn lpo.api:app            # serves http://localhost:8000
```

The Vite dev server proxies `/api` → `http://localhost:8000` (configurable via
`VITE_API_TARGET`). The backend allows the dev origin via CORS by default
(`LPO_CORS_ORIGINS`). The backend uses whatever provider is configured in
`.env` (`LPO_PROVIDER=fireworks` with a `FIREWORKS_API_KEY`, or `mock`).

## Build

```bash
npm run build        # tsc --noEmit && vite build  -> dist/
npm run preview      # serve the production build
```

For a static deploy hitting a hosted backend, set `VITE_API_BASE` (e.g.
`https://lpo.example.com`) at build time so the app calls that origin directly.

## Regenerating the README screenshots

The three guide screenshots in the root README are produced by Playwright in
Demo mode:

```bash
npm run build
npm run preview &                 # serves dist/ on :4173
npm run screenshots               # -> ../docs/screenshots/*.png
```

(Playwright needs a Chromium with its system libraries; `npx playwright install
--with-deps chromium` on a machine where you can install packages.)

## Structure

| File | Role |
|------|------|
| `src/types.ts` | TS mirrors of the LP IR + SolverResult contract |
| `src/api.ts` | `solve`/`confirm` clients + a faithful in-browser demo API |
| `src/demoData.ts` | the real Bradley run, for Demo mode |
| `src/lpGeometry.ts` | feasible-region polygon via half-plane clipping |
| `src/components/IrBreakdown.tsx` | prompt → LP elements, with provenance |
| `src/components/LpGraph.tsx` | the SVG feasible-region plot |
| `src/components/ResultPanel.tsx` | answer, bottlenecks, shadow prices, explanation |
| `src/App.tsx` | the Describe → Review → Solution state machine |

Models with more than two variables are solved exactly but can't be drawn as a
2-D region; the graph panel explains this and the answer panel still shows the
full solution.
