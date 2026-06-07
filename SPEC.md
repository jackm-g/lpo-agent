# LPO Agent — Software Engineering Specification

**Component:** Linear Programming Optimization (LPO) Agent
**Version:** 0.2 (draft)
**Owner:** TBD
**Status:** For review

**Changes in v0.2:** Introduced a provider-agnostic LLM interface (Section 6.6) so the formulation and explanation backends are swappable. Fireworks AI is the only configured provider for now (Section 8). Reframed model selection around a cost-versus-quality decision rule (Section 3). Documented Gemini for Government on Vertex AI as a future accredited backend (Section 3.3, Section 8.1).

-----

## 1. Purpose and scope

The LPO Agent turns a natural-language decision question into a formal linear (or mixed-integer linear) program, solves it with a deterministic solver, and returns a plain-language explanation grounded in the solver output. The agent does not do arithmetic. It does two language jobs: formulation (English to a formal model) and explanation (solver output back to English). A classical solver does everything in between.

In scope:

- Translate a question plus structured context into a linear program intermediate representation (LP IR).
- Validate the IR deterministically and gate on a human-readable restatement.
- Solve LP and MILP problems and extract primal solution, dual values, slacks, and sensitivity ranges.
- Explain the result, including binding constraints and shadow prices, grounded strictly in solver numbers.
- Recover from infeasible and unbounded results by diagnosing and reformulating, with a bounded retry budget.

Out of scope for v0.2:

- Nonlinear, quadratic, or stochastic programming.
- Multi-objective optimization beyond a single weighted objective.
- Automatic data retrieval. Numeric parameters arrive in the request context or via clarification.
- Fine-tuning the model. v0.2 uses the hosted instruction-tuned model as-is.

## 2. Goals and non-goals

Goals:

- Correct formulation is the primary quality metric. A wrong-but-feasible model is the worst outcome and the main thing the design defends against.
- Every constraint is traceable to a span of the source question (provenance).
- Syntactic validity of model output is guaranteed by schema-constrained generation, not by prompt pleading.
- The system is auditable. Every run logs the question, the IR, the solver result, and the explanation.

Non-goals:

- Lowest possible latency. Correctness and auditability win over speed in v0.2.
- Open-ended chat. The agent is a constrained pipeline, not a general assistant.

## 3. Provider strategy and model selection

The system is provider-agnostic. All model calls go through a single provider interface (Section 6.6), so the formulation and explanation backends can be swapped by configuration without touching the orchestrator, validation, solver, or data model. Exactly one provider is configured at a time.

### 3.1 Current provider: Fireworks AI

For now the only wired-up provider is Fireworks AI (OpenAI-compatible inference API). Concrete models:

| Role | Model | Fireworks model ID | Rationale |
|------|-------|--------------------|-----------|
| Formulation (primary) | Gemma 4 31B IT | `accounts/fireworks/models/gemma-4-31b-it` | Native function calling, configurable thinking mode, 256K context. Formulation is the hard reasoning step and wants the strongest model. |
| Explanation | Gemma 4 26B A4B IT | `accounts/fireworks/models/gemma-4-26b-a4b-it` | MoE (3.8B active) is cheaper and faster. Explanation is paraphrase of solver fields, so a lighter model suffices. |
| Cost-optimized fallback | Gemma 4 31B IT NVFP4 | `accounts/fireworks/models/gemma-4-31b-it-nvfp4` | 4-bit quantized 31B. Evaluate formulation accuracy before adopting. |

Notes:

- Both roles can run on a single model to simplify ops. Splitting is a cost optimization, not a requirement.
- Confirm exact model ID strings against the Fireworks catalog before deployment. IDs follow `accounts/fireworks/models/<slug>`.
- "Latest Gemma 4" is ambiguous. The newest weight release is the unified encoder-free 12B; its availability on Fireworks serverless was unconfirmed at spec time. If it is serverless and exposes function calling plus thinking mode, add it to the formulation eval set (Section 11) and adopt only if it matches or beats 31B IT on formulation accuracy. Do not assume the newer or smaller model is better for formulation.

### 3.2 Cost-versus-quality decision rule

Cost is not the binding constraint for this agent. Per-request token volume is small (a question, the schema, a few examples in; a small JSON model and a short explanation out), and expected request volume is low. The absolute dollar gap between the cheapest open model and a frontier model is trivial at this scale. Decide the formulation model on formulation accuracy against the golden set (Section 11), not on token price. Specifically:

- Thinking/reasoning mode is the primary quality lever, more than raw model size. Enable it for formulation.
- The real cost controls are: cache the static prompt prefix (system instructions, schema, few-shot), which is reused on every request; keep explanation on the cheap MoE model; and cap recovery-loop retries, which are the true cost multiplier.
- Tiered pattern: keep the open model on the standard path and escalate to a stronger model only if the eval shows it lowers the formulation error rate. A formulation error is a confidently wrong optimization, which costs far more than tokens.

### 3.3 Future provider: Gemini for Government (Vertex AI)

If the agent must operate on DoW or CUI data, the target backend is Gemini for Government on Vertex AI, which is authorized at FedRAMP High and DoD IL5 inside an Assured Workloads boundary, with data sovereignty and no training on tenant data. A commercial Fireworks endpoint does not carry that authorization. The provider interface (Section 6.6) makes this a backend swap: Gemini enforces the same LP IR via `responseJsonSchema` (full JSON Schema) or the OpenAPI-subset `responseSchema`, and supports native function calling. Not implemented in v0.2. See Section 8.1 for the migration notes.

## 4. Architecture

Five stages. The model owns Formulate and Explain. Deterministic code owns everything else, including the loop.

```
Question + context
        │
        ▼
   Formulate        (LLM provider, thinking mode, schema-constrained LP IR)
        │
        ▼
   Validate         (deterministic schema + semantic checks; human restatement gate)
        │
        ▼
    Solve           (HiGHS via PuLP, deterministic; returns primal, duals, slacks, ranges)
        │
        ├── optimal ──────────► Explain (LLM provider, grounded in solver result) ──► response
        │
        └── infeasible/unbounded ──► Diagnose (IIS / unbounded ray) ──► back to Formulate
                                     (bounded retries, then escalate to human)
```

Component boundaries:

- **Orchestrator** owns control flow, retry budget, conversation state, and the human-confirmation gate. Stateless across requests except for an in-memory message list scoped to one run.
- **Formulation service** is the only component that prompts the model for a model. Output is schema-constrained.
- **Validation layer** is pure functions, no network calls.
- **Solver service** wraps HiGHS. No LLM involvement.
- **Explanation service** prompts the model to narrate, with the solver result as the only source of numbers.
- **Provider layer** is the only component that talks to an LLM API. It exposes a backend-neutral interface (Section 6.6). Formulation and Explanation call it rather than any vendor SDK directly, so swapping providers is a configuration change confined to this layer.

## 5. Data model

### 5.1 LP IR (the contract between the model and the solver)

The model emits this structure under the active provider's structured-output mechanism (Fireworks `response_format`; Gemini `responseJsonSchema`). The schema itself is provider-neutral and is the single source of truth (Section 6.6). The `source` field on every constraint is mandatory and carries the span of the question that justifies the constraint.

See `lpo/models.py` — the JSON Schema is generated from the Pydantic models via `lp_ir_schema()`.

Worked instance (the recon/resupply example) lives in `goldens/recon_resupply.json`.

### 5.2 SolverResult

`shadow_price_basis` is critical. Duality is defined for continuous LP, not for integer programs. See Section 7.3. Modeled in `lpo/models.py::SolverResult`.

### 5.3 External API

Request: `{question, context, require_human_confirmation, max_retries}`.
Success: `{status, ir, result, explanation, restatement, trace_id}`.
Clarification/escalation: `{status: need_info|escalated, message, trace_id}`.
See `lpo/api.py` (two-call confirmation: `/v1/solve` then `/v1/confirm`).

## 6. Component specifications

### 6.1 Formulation service

Responsibility: produce a valid LP IR or a `need_info` request. This is the only creative step and the main risk surface.

- Schema-constrained generation against the LP IR (Section 5.1).
- Reasoning/thinking mode: enabled. Capture the reasoning trace separately from the JSON payload; log it as a diagnostic field.
- `temperature`: 0.0. Formulation must be deterministic.
- Token budget set generously (e.g. 4096). Treat truncation (`finish_reason=length`) as a validation failure and retry with a higher limit.

System prompt: state the role (convert, never solve); embed the schema and 2–3 few-shot examples including one with an implicit constraint and one deliberately underspecified example whose correct output is `status=need_info`; require a `source` on every constraint; return `need_info` rather than invent numbers or linearize nonlinearity silently.

### 6.2 Validation layer

Deterministic, no model calls. Checks: schema conformance; reference integrity; numeric sanity; enum legality; uniqueness; provenance coverage (advisory); linearity. Plus the human confirmation gate: render the IR to one plain-language paragraph (the `restatement`) and pause for approval when `require_human_confirmation` is true. The restatement is always generated and logged.

### 6.3 Solver service

Deterministic. Wraps HiGHS (PuLP). Build the model, set integrality, solve. Extract status, objective, variable values, per-constraint LHS/slack/binding (tolerance 1e-6). Dual values and sensitivity: see Section 7.3. On infeasible compute an IIS; on unbounded identify the direction.

### 6.4 Explanation service

Narrate the SolverResult; no new numbers. Use the cheaper explanation model. Every number must come from the SolverResult. Cover the decision, binding vs slack constraints, shadow prices (with the `shadow_price_basis` caveat for integer models), and the sensitivity range as the honest limit. Optional critic pass checks the explanation against the result.

### 6.5 Orchestrator and recovery loop

The retry budget is mandatory. A model that reformulates into the same infeasibility repeatedly will loop without it. See `lpo/orchestrator.py`.

### 6.6 Provider layer (LLM backend interface)

All LLM access goes through one narrow interface (`LlmProvider`). Nothing else imports a vendor SDK or knows a model ID. The LP IR JSON Schema is the single, provider-neutral source of truth, generated from the Pydantic model; each adapter translates it into that provider's structured-output mechanism. `formulate` returns parsed, schema-valid JSON or raises; `explain` returns prose. A provider is selected by configuration. Capability-aware fallback: if a future provider lacks strict schema, run a parse-and-repair loop. Adapters: `FireworksProvider` (implemented), `VertexGeminiProvider` (not implemented).

## 7. Key technical decisions and caveats

- **7.1 Declarative extraction over code generation.** The model emits the LP as data against a fixed schema, not solver code. A hallucinated constraint is visible in the IR.
- **7.2 Structured output enforces syntax, not semantics.** A flipped inequality is still valid JSON. Defenses: provenance, the restatement gate, the eval set. Most risk lives here.
- **7.3 Integer programs do not have shadow prices.** Solve the MILP for the decision; separately solve the LP relaxation and report its duals labelled `shadow_price_basis="lp_relaxation"`, with the explanation stating these are directional indicators. For continuous models report exact duals (`"lp"`).
- **7.4 The solver is the source of truth for all numbers.** The model never computes; the explanation paraphrases. Arithmetic hallucination is structurally impossible in the output.

## 8. Provider implementation: Fireworks AI (current)

See `lpo/providers/fireworks.py`. Endpoint `https://api.fireworks.ai/inference/v1/chat/completions` (OpenAI-compatible). Auth `Authorization: Bearer ${FIREWORKS_API_KEY}` (key in a secret manager, never in source). Structured output via `response_format` carrying the LP IR JSON Schema. Reliability: detect `finish_reason=length` and retry with higher `max_tokens`; exponential backoff on 429/5xx with a capped attempt count; generous timeouts for thinking mode; track tokens per stage.

### 8.1 Migration: adding Gemini for Government (Vertex AI)

Implement `VertexGeminiProvider` against the Section 6.6 interface. No other component changes. Vertex `generateContent` inside an Assured Workloads (FedRAMP High / IL5) project; Google Cloud credentials, not a static key; LP IR via `responseJsonSchema` (fallback `responseSchema`). Keep the solver and orchestration inside the boundary.

## 9. Failure modes and mitigations

| Failure | Visibility | Mitigation |
|---------|-----------|------------|
| Malformed model output | High | Schema-constrained generation. |
| Truncated JSON (token limit) | Medium | Detect `finish_reason=length`, retry with higher `max_tokens`. |
| Flipped inequality or wrong sense | Low | Human restatement gate; sometimes an absurd/unbounded result. |
| Missing constraint | Very low | Provenance audit, restatement gate, eval set. Most dangerous case. |
| Phantom (invented) constraint | Low | Provenance: the model cannot cite a source span. |
| Nonlinearity smuggled in | Low | Instruction to return `need_info`; linearity check in validation. |
| Infeasible loop | Medium | IIS feedback plus bounded retry budget, then escalate. |
| Integer shadow-price overclaim | Low | `shadow_price_basis` labeling and explanation caveat (7.3). |

## 10. Observability

Per run, log under a `trace_id`: question and context; full LP IR plus the separate thinking trace; restatement and the human confirmation decision; SolverResult; final explanation and any critic flags; token counts and latency per stage. The provenance map (constraint → source span) is the audit backbone. See `lpo/observability.py`.

## 11. Evaluation

- **Formulation accuracy** is the headline metric: a golden set of question/IR pairs, scored on IR equivalence (normalize variable names and constraint order). See `lpo/eval.py::ir_signature`.
- **Solver correctness** by re-substituting the returned solution into all constraints (`solution_satisfies_constraints`).
- **Explanation faithfulness**: every number in the explanation appears in the SolverResult (`grounded_numbers`).
- Run against 31B IT, 26B A4B, and any serverless 12B variant. Adopt on accuracy evidence, not recency.

## 12. Security and data handling

The model never executes code and never computes results. API keys in a secret manager; no keys in logs or source. Treat question and context as untrusted; the model has no external tools in v0.2, limiting prompt-injection blast radius to "produce a bad IR," which validation and the confirmation gate catch. For sensitive deployments prefer a dedicated/on-demand Fireworks deployment over shared serverless, and confirm data-retention terms.

## 13. Tech stack

Python 3.11+; PuLP with HiGHS; Pydantic (JSON Schema generated from the models); `requests`/`httpx`; provider adapters behind the Section 6.6 interface; containerized REST service.

## 14. Phasing

- **Phase 1:** Formulation + validation + solver, no recovery loop, confirmation gate always on, pure LP. Prove formulation accuracy on the golden set.
- **Phase 2:** MILP, integer shadow-price handling (7.3), explanation service.
- **Phase 3:** Recovery loop (IIS feedback, bounded retries) and critic pass.
- **Phase 4:** Cost optimization (model split, quantized fallback), optional confirmation bypass for low-stakes batch use.

## 15. Open questions

1. Is a Gemma 4 12B variant available on Fireworks serverless with function calling + thinking mode?
2. Exact Fireworks field names for the schema in `response_format` and the thinking-mode toggle.
3. Confirmation gate UX: synchronous pause vs a two-call pattern. (This implementation uses the two-call pattern.)
4. Default `require_human_confirmation` per deployment tier.
5. Provider portability: do few-shot/system prompts need per-provider tuning?
6. For Vertex: does the authorized surface expose `responseJsonSchema` or only `responseSchema`?
