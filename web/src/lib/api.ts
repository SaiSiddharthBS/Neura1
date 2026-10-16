export type Path = { nodes: string[]; qty: number; refdes: string[]; blocked_by: string[] };
export type WhereUsed = {
  product: string; revision: string; status: string; applicable: boolean;
  qty_per_unit: number; qty_if_built: number; paths: Path[];
};
export type Order = {
  order: string; qty: number; due: string; penalty: string; customer: string;
  customer_id: string; account_manager: string | null;
};
export type Build = {
  build: string; revision: string; build_qty: number; planned_date: string; planner: string | null;
  orders: Order[]; parts_needed: number; from_stock: number; shortfall: number;
  supply_eta_if_ordered_today: string | null; at_risk: boolean;
};
export type EvidenceRef = {
  chunk: string; source: string; title: string; quote?: string; page?: number | null;
  author?: string | null; ts?: string | null;
};
export type Decision = {
  id: string; subject: string; outcome: string; summary: string; reason: string | null;
  decided_at: string | null; authority: string; status: string; decided_by: string | null; extracted_by?: string | null;
  applies_to: string[]; evidence: EvidenceRef[];
};
export type QuoteRow = {
  id: string; supplier: string; unit_price: string; currency: string; moq: number; lead_weeks: number;
  valid_from: string; valid_until: string; authority: string; source: string;
};
export type Alternate = {
  id: string; name: string; manufacturer: string; basis: string; note: string;
  quotes: QuoteRow[]; decisions: Decision[]; status: "approved" | "rejected" | "pending_review" | "unqualified";
};
export type Dependent = {
  id: string; kind: string; name: string; note: string; owner: string | null; team: string | null;
  evidence: EvidenceRef[];
};
export type Action = { kind: string; target: string; owner: string | null; title: string; why: string; cites: string[] };
export type Cost = {
  currency: string; gross_need: number; free_stock: number; net_need: number; purchase_qty: number;
  baseline_quote: string; baseline_unit_price: number; new_unit_price: number; material_delta: number;
  one_time_total: number; total_delta: number; formula: string; assumptions: string[]; excluded: string[];
  one_time: { label: string; amount: number; currency: string; source: string }[];
};
export type TraceStep = { name: string; cypher: string; params: Record<string, unknown>; rows: number; ms: number };
export type GraphNode = { id: string; type: string; label: string; [k: string]: unknown };
export type GraphEdge = { source: string; target: string; label: string };
export type Investigation = {
  id: string; created_at: string; approved_by: string; cost_total: string | null; currency: string | null;
  actions: { id: string; kind: string; title: string; status: string; owner: string | null; created_at: string }[];
};
export type ImpactReport = {
  status: "ok";
  change: { item: string; new_unit_price: number | null; currency: string; effective_date: string | null;
            lead_weeks: number | null; as_of: string; source_id: string | null };
  part: { id: string; name: string; mpn: string; manufacturer: string; on_hand: number; allocated: number; owner: string | null };
  where_used: WhereUsed[]; builds: Build[];
  field_units: { shipment: string; revision: string; status: string; qty: number; shipped_on: string; customer: string }[];
  dependents: Dependent[]; assemblies: { item: string; name: string; revisions: string[]; owner: string | null }[];
  quotes: QuoteRow[]; alternates: Alternate[]; decisions: Decision[];
  cost: Cost | null; cost_error: string | null; actions: Action[]; assumptions: string[];
  trace: TraceStep[]; graph: { nodes: GraphNode[]; edges: GraphEdge[] }; investigation: Investigation | null;
  changes_since_approval: string[];
};
export type Unresolved = { status: "unresolved"; item: string; candidates: unknown[] };

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(typeof body === "object" && body && "detail" in body ? JSON.stringify((body as { detail: unknown }).detail) : String(status));
  }
}

function passcode(): string {
  try {
    return localStorage.getItem("neura1-passcode") ?? "";
  } catch {
    return "";
  }
}

export async function api<T>(path: string, init?: RequestInit & { write?: boolean }): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (init?.write) headers["x-demo-passcode"] = passcode();
  const res = await fetch(path, { ...init, headers: { ...headers, ...(init?.headers as Record<string, string>) } });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

export const inr = (n: number | string | null | undefined, currency = "INR") =>
  n === null || n === undefined
    ? "—"
    : new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(n));
