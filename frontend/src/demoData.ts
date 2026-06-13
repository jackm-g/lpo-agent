// Built-in demo dataset — the real Bradley motor-pool run (deepseek-v4-pro +
// gpt-oss-120b), so the UI is fully explorable with no backend running.
import type { InfoResponse, LpIr, SuccessResponse } from "./types";

export const DEMO_IR: LpIr = {
  status: "formulated",
  sense: "maximize",
  variables: [
    { name: "svc", meaning: "number of scheduled services (PMCS)", lower: 0, upper: null, integer: true },
    { name: "flr", meaning: "number of field level repairs (NMC)", lower: 0, upper: null, integer: true },
  ],
  objective: [
    { var: "svc", coef: 30 },
    { var: "flr", coef: 75 },
  ],
  constraints: [
    {
      name: "mech_hrs",
      terms: [{ var: "svc", coef: 20 }, { var: "flr", coef: 40 }],
      op: "<=",
      rhs: 800,
      source: "svc = 20 mech hrs, FLR = 40, got 800 91M hrs this wk.",
    },
    {
      name: "parts_budget",
      terms: [{ var: "svc", coef: 1000 }, { var: "flr", coef: 3000 }],
      op: "<=",
      rhs: 45000,
      source: "parts: svc ~1k cl ix, FLR ~3k, budget 45k.",
    },
    {
      name: "pp_limit",
      terms: [{ var: "flr", coef: 1 }],
      op: "<=",
      rhs: 12,
      source: "FLRs each need a rebuilt PP, we got 12 (svcs dont need one).",
    },
  ],
};

const RESTATEMENT = `We want to maximize 30×(scheduled services) + 75×(field-level repairs), by choosing:
  - svc = number of scheduled services (PMCS) (integer, ≥ 0).
  - flr = number of field level repairs (NMC) (integer, ≥ 0).
Subject to:
  - mech_hrs: 20×svc + 40×flr must be at most 800.
  - parts_budget: 1000×svc + 3000×flr must be at most 45000.
  - pp_limit: 1×flr must be at most 12.`;

export const DEMO_SOLVE: InfoResponse = {
  status: "need_confirmation",
  message: "Review the restatement and approve before solving.",
  trace_id: "demo-001",
  ir: DEMO_IR,
  restatement: RESTATEMENT,
};

export const DEMO_CONFIRM: SuccessResponse = {
  status: "optimal",
  ir: DEMO_IR,
  restatement: RESTATEMENT,
  trace_id: "demo-001",
  result: {
    status: "optimal",
    is_integer_model: true,
    objective_value: 1275,
    variables: { svc: 30, flr: 5 },
    constraints: [
      { name: "mech_hrs", lhs_value: 800, rhs: 800, binding: true, slack: 0, shadow_price: 0.75, shadow_price_basis: "lp_relaxation" },
      { name: "parts_budget", lhs_value: 45000, rhs: 45000, binding: true, slack: 0, shadow_price: 0.015, shadow_price_basis: "lp_relaxation" },
      { name: "pp_limit", lhs_value: 5, rhs: 12, binding: false, slack: 7, shadow_price: 0, shadow_price_basis: "lp_relaxation" },
    ],
    sensitivity: null,
    diagnosis: null,
  },
  explanation:
    "The optimal plan is to complete 30 scheduled services and 5 field-level repairs, for a total readiness-priority value of 1275. Labor (800 of 800 mech-hours) and Class IX parts ($45,000 of $45,000) are both fully consumed — they are the bottlenecks. Rebuilt powerpacks are not limiting: only 5 of 12 are used, leaving 7 spare. The shadow prices (labor ≈ 0.75 pts per mech-hour, parts ≈ 0.015 pts per dollar) are LP-relaxation directional indicators, not exact marginal values for this integer model. To deliver more readiness you would need more mechanic-hours or parts budget; more powerpacks would not help this week.",
};

export const DEMO_NEED_INFO: InfoResponse = {
  status: "need_info",
  message:
    "What is the total available mechanic (wrench) time for the week? It is described as the chokepoint but no number is given.",
  trace_id: "demo-002",
};

export const DEMO_PROMPT = `planning the motor pool week for our bradleys. two work types - scheduled
svcs (pmcs) and field level repairs (the NMC ones). CO weights a FLR at 75
and a svc at 30, trying to maximize total. svc = 20 mech hrs, FLR = 40, got
800 91M hrs this wk. parts: svc ~1k cl ix, FLR ~3k, budget 45k. FLRs each
need a rebuilt PP, we got 12 (svcs dont need one). how many of each? whole
trucks`;
