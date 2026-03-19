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
  supplier_name: string | null; // populated by admin endpoints; null for supplier views
  triage_risk_level: string | null; // LOW | MEDIUM | HIGH | CRITICAL; set by AI triage
}

export interface InvoiceListFilters {
  statusFilter?: string;
  search?: string;
  supplierId?: string;
  dateFrom?: string; // YYYY-MM-DD
  dateTo?: string;   // YYYY-MM-DD
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

/** Admin-enriched invoice detail — includes supplier + contract name + AI triage. */
export interface AdminInvoiceDetail extends InvoiceDetail {
  supplier_name: string | null;
  contract_name: string | null;
  triage_risk_level: string | null; // LOW | MEDIUM | HIGH | CRITICAL
  triage_notes: string | null; // newline-separated risk factors
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
  mapping_confidence: string | null;
  raw_amount: string;
  /** AI suggestion for UNRECOGNIZED lines; null for classified-but-uncertain lines. */
  ai_classification_suggestion: AiClassificationSuggestion | null;
}

/** Admin supplier row */
export interface AdminSupplier {
  id: string;
  name: string;
  tax_id: string | null;
  is_active: boolean;
  contract_count: number;
  invoice_count: number;
  user_count: number;
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

export interface RateCardDetail {
  id: string;
  taxonomy_code: string;
  taxonomy_label: string | null;
  contracted_rate: string;
  max_units: string | null;
  is_all_inclusive: boolean;
  effective_from: string;
  effective_to: string | null;
}

export interface RateCardCreate {
  taxonomy_code: string;
  contracted_rate: string;
  max_units: string | null;
  is_all_inclusive: boolean;
  effective_from: string;
  effective_to: string | null;
}

export interface GuidelineDetail {
  id: string;
  taxonomy_code: string | null;
  domain: string | null;
  rule_type: string;
  rule_params: Record<string, unknown>;
  severity: string;
  narrative_source: string | null;
  is_active: boolean;
}

export interface GuidelineCreate {
  taxonomy_code: string | null;
  domain: string | null;
  rule_type: string;
  rule_params: Record<string, unknown>;
  severity: string;
  narrative_source: string | null;
}

export interface ContractCreate {
  supplier_id: string;
  name: string;
  effective_from: string;
  effective_to: string | null;
  geography_scope: string;
  state_codes: string[] | null;
  notes: string | null;
}

export interface ContractDetail extends AdminContract {
  state_codes: string[] | null;
  notes: string | null;
  rate_cards: RateCardDetail[];
  guidelines: GuidelineDetail[];
}

export interface ParsedContractResult {
  contract: {
    supplier_id: string;
    name: string;
    effective_from: string;
    effective_to: string | null;
    geography_scope: string;
    state_codes: string[] | null;
    notes: string | null;
  };
  rate_cards: RateCardCreate[];
  guidelines: GuidelineCreate[];
  extraction_notes: string;
}

export interface BulkApprovalResult {
  approved: number;
  skipped: number;
  approved_invoice_numbers: string[];
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
  /** AI-suggested resolution action (a ResolutionAction constant). Null until processed. */
  ai_recommendation: string | null;
  /** AI explanation shown to carrier. Null until processed. */
  ai_reasoning: string | null;
  /** AI assessment of supplier response: SUFFICIENT | INSUFFICIENT | PARTIAL. Null until supplier responds. */
  ai_response_assessment: string | null;
  /** AI explanation of the response assessment. Null until supplier responds. */
  ai_response_reasoning: string | null;
  /** Whether the carrier accepted the AI recommendation. Null if no AI rec existed. */
  ai_recommendation_accepted: boolean | null;
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

export interface AiClassificationSuggestion {
  verdict: "SUGGESTED" | "TAXONOMY_GAP" | "OUT_OF_SCOPE";
  /** Taxonomy code (SUGGESTED only; null otherwise) */
  suggested_code: string | null;
  /** Last segment of the code, e.g. "PROF_FEE" (SUGGESTED only; null otherwise) */
  suggested_billing_component: string | null;
  /** Confidence level (SUGGESTED only; null otherwise) */
  confidence: "HIGH" | "MEDIUM" | "LOW" | null;
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
  /** AI classification suggestion for UNRECOGNIZED lines. Null for classified lines. */
  ai_classification_suggestion: AiClassificationSuggestion | null;
}

// ── Status constants (mirrors Python enums) ───────────────────────────────────

// ── Analytics ─────────────────────────────────────────────────────────────────

export interface AnalyticsSummary {
  total_billed: string;
  total_approved: string;
  /** Billed minus approved on finalized invoices where raw > expected. */
  total_savings: string;
  open_exceptions: number;
  total_exceptions: number;
  invoice_status_counts: { status: string; count: number }[];
}

export interface SpendByDomain {
  domain: string;
  line_count: number;
  total_billed: string;
  total_approved: string;
}

export interface SpendBySupplier {
  supplier_id: string;
  supplier_name: string;
  invoice_count: number;
  total_billed: string;
  total_approved: string;
}

export interface SpendByTaxonomy {
  taxonomy_code: string;
  label: string | null;
  domain: string | null;
  line_count: number;
  total_billed: string;
  total_approved: string;
  /** Sum of raw_quantity across all lines for this code */
  total_quantity: string;
  /** Average billed amount per unit (total_billed / total_quantity); null if no quantity data */
  avg_billed_rate: string | null;
}

export interface ExceptionBreakdown {
  validation_type: string;
  count: number;
}

export interface RateGap {
  taxonomy_code: string;
  taxonomy_label: string | null;
  supplier_id: string;
  supplier_name: string;
  /** Number of open exceptions with required_action = ESTABLISH_CONTRACT_RATE */
  open_count: number;
  /** Total billed amount across all lines with this gap (Decimal as string) */
  total_billed: string;
}

export interface SupplierComparisonRow {
  taxonomy_code: string;
  taxonomy_label: string | null;
  supplier_id: string;
  supplier_name: string;
  invoice_count: number;
  total_billed: string;
  total_expected: string;
  total_savings: string;
  exception_rate: string;
}

export interface AiAccuracyByAction {
  action: string;
  /** Total exceptions where AI recommended this action */
  recommended: number;
  /** Subset that have been resolved (accepted or overridden) */
  resolved: number;
  /** Subset where carrier followed the AI recommendation */
  accepted: number;
  /** accepted / resolved, null if no resolved data yet */
  acceptance_rate: number | null;
}

export interface SpendByState {
  state: string;           // 2-char code, e.g. "CA"
  line_count: number;
  total_billed: string;
  total_approved: string;
}

export interface SpendByZip {
  zip: string;
  state: string | null;
  line_count: number;
  total_billed: string;
}

export interface SpendTrend {
  /** ISO month string, e.g. "2025-03" */
  period: string;
  invoice_count: number;
  total_billed: string;
  total_approved: string;
}

export interface ContractHealth {
  contract_id: string;
  contract_name: string;
  supplier_name: string;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  rate_card_count: number;
  invoice_count: number;
  exception_count: number;
  /** exception_count / invoice_count; 0 if no invoices */
  exception_rate: number;
  /** ACTIVE | EXPIRING_SOON | EXPIRED */
  expiry_status: string;
  /** Days until expiry (positive) or past expiry (negative); null = open-ended */
  days_to_expiry: number | null;
}

export interface SupplierScorecard {
  supplier_id: string;
  supplier_name: string;
  total_invoices: number;
  invoice_status_counts: Record<string, number>;
  total_billed: string;
  total_expected: string;
  total_savings: string;
  total_exceptions: number;
  exception_rate: number;
  auto_approval_rate: number;
  top_taxonomy_codes: {
    taxonomy_code: string;
    label: string | null;
    total_billed: string;
    line_count: number;
  }[];
  top_exception_types: {
    validation_type: string;
    count: number;
  }[];
}

export interface AiAccuracyStats {
  /** Total exceptions that received an AI recommendation */
  total_with_recommendation: number;
  /** Subset that have been resolved (carrier made a decision) */
  total_resolved: number;
  /** Subset where the carrier followed the AI recommendation */
  total_accepted: number;
  /** total_accepted / total_resolved — null if no resolved data yet */
  acceptance_rate: number | null;
  /** Per-action breakdown, ordered by recommendation frequency */
  by_recommended_action: AiAccuracyByAction[];
}

export interface SupplierAuditFinding {
  title: string;
  detail: string;
  severity: "INFO" | "WARNING" | "ERROR";
}

export interface SupplierAuditResult {
  risk_rating: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  findings: SupplierAuditFinding[];
  recommendations: string[];
}

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


// ── Carrier Team ──────────────────────────────────────────────────────────────

export interface CarrierUser {
  id: string;
  email: string;
  role: "CARRIER_ADMIN" | "CARRIER_REVIEWER";
  is_active: boolean;
  /** Taxonomy domain prefixes this auditor is responsible for. null = all domains. */
  category_scope: string[] | null;
  /** Supplier UUIDs this auditor is assigned to. null = all suppliers. */
  supplier_scope: string[] | null;
}

export interface CarrierUserCreate {
  email: string;
  password: string;
  role: "CARRIER_ADMIN" | "CARRIER_REVIEWER";
}

export interface UserScopeUpdate {
  category_scope: string[] | null;
  supplier_scope: string[] | null;
}
