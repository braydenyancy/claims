export interface User {
  id: number;
  username: string;
  role: string;
  can_create_claims: boolean;
}

export interface Option {
  value: string;
  label: string;
  tone?: string;
}

export interface StateCount extends Option {
  count: number;
}

export interface Summary {
  total: number;
  open_alerts: number;
  states: StateCount[];
}

export interface Meta {
  states: Option[];
  denial_reasons: Option[];
  registration_statuses: Option[];
}

export interface Field {
  name: string;
  type: "text" | "decimal" | "choice";
  choices: string[];
}

export interface AvailableAction {
  action: string;
  label: string;
  fields: Field[];
  blocked_reason: string | null;
}

export interface Registration {
  status: string;
  attempts?: number;
  last_error?: string;
  submission_id?: string;
  next_attempt_at?: string | null;
  can_retry?: boolean;
  can_reconcile?: boolean;
}

export interface Acknowledgement {
  actor: string | null;
  note: string;
  created_at: string;
}

export interface Alert {
  event_id: number;
  action: string;
  created_at: string;
  data: Record<string, unknown>;
  acknowledgement: Acknowledgement | null;
  can_acknowledge: boolean;
}

export interface ClaimSummary {
  id: number;
  reference: string;
  payer: string;
  service_date: string | null;
  billed_amount: string;
  state: string;
  version: number;
  has_open_alert: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ClaimDetail extends ClaimSummary {
  approved_amount: string | null;
  denial_reason: string;
  submission_id: string;
  available_actions: AvailableAction[];
  registration: Registration;
  can_edit: boolean;
  alerts: Alert[];
}

export interface ClaimEvent {
  id: number;
  action: string;
  from_state: string;
  to_state: string;
  actor: string | null;
  data: Record<string, unknown>;
  severity: "info" | "warning" | "alert";
  created_at: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ConflictBody {
  detail: string;
  current_state: string;
  current_version: number;
  last_event: ClaimEvent | null;
}

export interface ErrorBody {
  detail?: string;
  errors?: Record<string, string>;
  [field: string]: unknown;
}

export interface DraftInput {
  payer: string;
  service_date: string | null;
  billed_amount: string;
}
