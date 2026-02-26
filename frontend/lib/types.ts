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

export interface LineItemCarrierView extends LineItemSupplierView {
  taxonomy_code: string | null;
  taxonomy_label: string | null;
  billing_component: string | null;
  mapped_unit_model: string | null;
  mapping_confidence: string | null; // HIGH | MEDIUM | LOW
  mapped_rate: string | null;
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
} as const;

export type ResolutionAction =
  (typeof ResolutionActions)[keyof typeof ResolutionActions];

export const UserRoles = {
  SUPPLIER: "SUPPLIER",
  CARRIER_ADMIN: "CARRIER_ADMIN",
  CARRIER_REVIEWER: "CARRIER_REVIEWER",
  SYSTEM_ADMIN: "SYSTEM_ADMIN",
} as const;
