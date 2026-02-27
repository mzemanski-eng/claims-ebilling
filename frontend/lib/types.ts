// TypeScript interfaces matching the FastAPI Pydantic schemas exactly.
// Decimal fields come back as strings (JSON serialisation of Python Decimal).

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: string;
  supplier_id: string | null;
  carrier_id: string | null;
}

export interface UserInfo {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  supplier_id: string | null;
  supplier_name: string | null;
  carrier_id: string | null;
  carrier_name: string | null;
}

// ── Invoice ───────────────────────────────────────────────────────────────────

export interface ValidationSummary {
  total_lines: number;
  lines_validated: number;
  lines_with_exceptions: number;
  lines_pending_review: number;
  total_billed: string;
  total_payable: string;
  total_in_dispute: string;
  lines_denied: number;
  total_denied: string;
}

export interface InvoiceListItem {
  id: string;
  invoice_number: string;
  invoice_date: string; // ISO date
  status: string;
  current_version: number;
  submitted_at: string | null;
  total_billed: string | null;
  exception_count: number;
}

export interface InvoiceDetail {
  id: string;
  supplier_id: string;
  contract_id: string;
  invoice_number: string;
  invoice_date: string;
  status: string;
  current_version: number;
  file_format: string | null;
  submitted_at: string | null;
  submission_notes: string | null;
  created_at: string;
  updated_at: string;
  validation_summary: ValidationSummary | null;
}

/** Admin-enriched invoice detail — includes supplier + contract name. */
export interface AdminInvoiceDetail extends InvoiceDetail {
  supplier_name: string | null;
  contract_name: string | null;
}

/** One row from the mapping review queue. */
export interface MappingQueueItem {
  line_item_id: string;
  invoice_id: string;
  line_number: number;
  raw_description: string;
  raw_code: string | null;
  taxonomy_code: string | null;
  billing_component: string | null;
  mapping_confidence: string;
  raw_amount: string;
}

/** Admin supplier row */
export interface AdminSupplier {
  id: string;
  name: string;
  tax_id: string | null;
  is_active: boolean;
  contract_count: number;
  invoice_count: number;
}

/** Admin contract row */
export interface AdminContract {
  id: string;
  name: string;
  supplier_id: string;
  supplier_name: string | null;
  carrier_id: string;
  effective_from: string;
  effective_to: string | null;
  geography_scope: string;
  is_active: boolean;
  rate_card_count: number;
  guideline_count: number;
}

export interface InvoiceUploadResponse {
  invoice_id: string;
  status: string;
  message: string;
  version: number;
}

export interface InvoiceCreate {
  contract_id: string;
  invoice_number: string;
  invoice_date: string; // ISO date
  submission_notes?: string;
}

// ── Validation ────────────────────────────────────────────────────────────────

export interface ValidationResult {
  status: string; // PASS | FAIL | WARNING
  severity: string; // ERROR | WARNING | INFO
  message: string;
  expected_value: string | null;
  actual_value: string | null;
  required_action: string;
}

export interface ExceptionView {
  exception_id: string;
  status: string;
  message: string;
  severity: string;
  required_action: string;
  supplier_response: string | null;
  resolution_action: string | null;
}

// ── Line Items ────────────────────────────────────────────────────────────────

export interface LineItemSupplierView {
  id: string;
  line_number: number;
  status: string;
  raw_description: string;
  raw_amount: string;
  raw_quantity: string;
  raw_unit: string | null;
  claim_number: string | null;
  service_date: string | null;
  expected_amount: string | null;
  validations: ValidationResult[];
  exceptions: ExceptionView[];
  needs_review: boolean;
}

export interface AiDescriptionAssessment {
  score: "ALIGNED" | "PARTIAL" | "MISALIGNED";
  rationale: string;
  model: string;
}

export interface LineItemCarrierView extends LineItemSupplierView {
  taxonomy_code: string | null;
  taxonomy_label: string | null;
  billing_component: string | null;
  mapped_unit_model: string | null;
  mapping_confidence: string | null; // HIGH | MEDIUM | LOW
  mapped_rate: string | null;
  /** AI description alignment assessment. Null when API key not set or call failed. */
  ai_description_assessment: AiDescriptionAssessment | null;
}

// ── Status constants (mirrors Python enums) ───────────────────────────────────

export const SubmissionStatus = {
  DRAFT: "DRAFT",
  SUBMITTED: "SUBMITTED",
  PROCESSING: "PROCESSING",
  REVIEW_REQUIRED: "REVIEW_REQUIRED",
  SUPPLIER_RESPONDED: "SUPPLIER_RESPONDED",
  PENDING_CARRIER_REVIEW: "PENDING_CARRIER_REVIEW",
  CARRIER_REVIEWING: "CARRIER_REVIEWING",
  APPROVED: "APPROVED",
  DISPUTED: "DISPUTED",
  EXPORTED: "EXPORTED",
  WITHDRAWN: "WITHDRAWN",
} as const;

export type SubmissionStatusType =
  (typeof SubmissionStatus)[keyof typeof SubmissionStatus];

export const LineItemStatusValues = {
  PENDING: "PENDING",
  CLASSIFIED: "CLASSIFIED",
  VALIDATED: "VALIDATED",
  EXCEPTION: "EXCEPTION",
  OVERRIDE: "OVERRIDE",
  APPROVED: "APPROVED",
  DISPUTED: "DISPUTED",
  RESOLVED: "RESOLVED",
  DENIED: "DENIED",
} as const;

export const ExceptionStatusValues = {
  OPEN: "OPEN",
  SUPPLIER_RESPONDED: "SUPPLIER_RESPONDED",
  CARRIER_REVIEWING: "CARRIER_REVIEWING",
  RESOLVED: "RESOLVED",
  WAIVED: "WAIVED",
} as const;

export const ResolutionActions = {
  WAIVED: "WAIVED",
  HELD_CONTRACT_RATE: "HELD_CONTRACT_RATE",
  RECLASSIFIED: "RECLASSIFIED",
  ACCEPTED_REDUCTION: "ACCEPTED_REDUCTION",
  DENIED: "DENIED",
} as const;

export type ResolutionAction =
  (typeof ResolutionActions)[keyof typeof ResolutionActions];

export const UserRoles = {
  SUPPLIER: "SUPPLIER",
  CARRIER_ADMIN: "CARRIER_ADMIN",
  CARRIER_REVIEWER: "CARRIER_REVIEWER",
  SYSTEM_ADMIN: "SYSTEM_ADMIN",
} as const;
