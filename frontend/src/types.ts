// Mirrors the Pydantic models in lpo/models.py (the LP IR contract + SolverResult).

export type Sense = "maximize" | "minimize";
export type Op = "<=" | ">=" | "==";

export interface Variable {
  name: string;
  meaning: string;
  lower: number | null;
  upper?: number | null;
  integer: boolean;
}

export interface Term {
  var: string;
  coef: number;
}

export interface Constraint {
  name: string;
  terms: Term[];
  op: Op;
  rhs: number;
  source: string;
}

export interface LpIr {
  status: "formulated" | "need_info";
  need_info?: string | null;
  sense: Sense;
  variables: Variable[];
  objective: Term[];
  constraints: Constraint[];
}

export type ShadowPriceBasis = "lp" | "lp_relaxation" | "none";

export interface ConstraintResult {
  name: string;
  lhs_value: number;
  rhs: number;
  binding: boolean;
  slack: number;
  shadow_price: number | null;
  shadow_price_basis: ShadowPriceBasis;
}

export interface Diagnosis {
  type: "iis" | "unbounded_ray" | "none";
  constraints: string[];
  variables: string[];
  detail?: string | null;
}

export interface SolverResult {
  status: "optimal" | "infeasible" | "unbounded" | "error";
  is_integer_model: boolean;
  objective_value: number | null;
  variables: Record<string, number>;
  constraints: ConstraintResult[];
  sensitivity?: Record<string, unknown> | null;
  diagnosis?: Diagnosis | null;
  error?: string | null;
}

// ---- API responses (Section 5.3) ----------------------------------------- //
export interface SuccessResponse {
  status: "optimal";
  ir: LpIr;
  result: SolverResult;
  explanation: string;
  restatement: string;
  trace_id: string;
}

export interface InfoResponse {
  status: "need_info" | "escalated" | "need_confirmation";
  message: string;
  trace_id: string;
  ir?: LpIr | null;
  restatement?: string | null;
}

export type ApiResponse = SuccessResponse | InfoResponse;

export function isSuccess(r: ApiResponse): r is SuccessResponse {
  return r.status === "optimal";
}
