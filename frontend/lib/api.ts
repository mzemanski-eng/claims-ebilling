/**
 * Typed API client for the Claims eBilling backend.
 *
 * All calls inject the Authorization: Bearer token automatically.
 * 401 responses clear the token and redirect to /login.
 *
 * NOTE: login() is the only exception — it must use
 * application/x-www-form-urlencoded (OAuth2PasswordRequestForm).
 */

import { clearToken, getToken } from "./auth";
import type {
  AdminContract,
  AdminInvoiceDetail,
  AdminSupplier,
  CarrierUser,
  CarrierUserCreate,
  UserScopeUpdate,
  SeedDemoJobStatus,
  AiAccuracyStats,
  AnalyticsSummary,
  BulkApprovalResult,
  ClassificationApproveRequest,
  ClassificationApproveResult,
  ClassificationQueueItem,
  ClassificationRejectRequest,
  ClassificationStats,
  ContractCreate,
  ContractDetail,
  ContractHealth,
  ExceptionBreakdown,
  ExceptionView,
  GuidelineCreate,
  GuidelineDetail,
  InvoiceCreate,
  InvoiceDetail,
  InvoiceListFilters,
  InvoiceListItem,
  InvoiceUploadResponse,
  LineItemCarrierView,
  LineItemSupplierView,
  MappingQueueItem,
  ParsedContractResult,
  RateCardCreate,
  RateCardDetail,
  RateGap,
  SpendByDomain,
  SpendByState,
  SpendBySupplier,
  SpendByTaxonomy,
  SpendByZip,
  SpendTrend,
  SupplierAuditResult,
  SupplierComparisonRow,
  SupplierScorecard,
  TokenResponse,
  UserInfo,
  AnalyticsFilters,
  SavingsRealization,
  UtilizationRow,
  ClaimStackingRow,
  RateBenchmarkRow,
  ReviewQueueGroup,
  MappingInsights,
  ValueSummary,
  CarrierSettings,
  SupplierProfile,
  SupplierProfileUpdate,
  SupplierDocument,
  TaxonomyImportResult,
  Vertical,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Session expired — please log in again.");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>;
    const detail =
      typeof body.detail === "string" ? body.detail : res.statusText;
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

/**
 * Login — uses form encoding because FastAPI reads OAuth2PasswordRequestForm.
 * Do NOT change to JSON.
 */
export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const form = new URLSearchParams({ username: email, password });
  const res = await fetch(`${BASE_URL}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>;
    const detail =
      typeof body.detail === "string" ? body.detail : "Invalid credentials";
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<TokenResponse>;
}

export function getMe(): Promise<UserInfo> {
  return apiFetch<UserInfo>("/auth/me");
}

// ── Supplier ──────────────────────────────────────────────────────────────────

export function listSupplierInvoices(): Promise<InvoiceListItem[]> {
  return apiFetch<InvoiceListItem[]>("/supplier/invoices");
}

export function getSupplierInvoice(id: string): Promise<InvoiceDetail> {
  return apiFetch<InvoiceDetail>(`/supplier/invoices/${id}`);
}

export function getSupplierInvoiceLines(
  id: string,
): Promise<LineItemSupplierView[]> {
  return apiFetch<LineItemSupplierView[]>(`/supplier/invoices/${id}/lines`);
}

export function createInvoice(
  payload: InvoiceCreate,
): Promise<InvoiceDetail> {
  return apiFetch<InvoiceDetail>("/supplier/invoices", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Upload an invoice file. Uses FormData — do NOT set Content-Type manually. */
export async function uploadInvoiceFile(
  invoiceId: string,
  file: File,
): Promise<InvoiceUploadResponse> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${BASE_URL}/supplier/invoices/${invoiceId}/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>;
    const detail =
      typeof body.detail === "string" ? body.detail : "Upload failed";
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<InvoiceUploadResponse>;
}

/** Resubmit an existing invoice with a corrected file. Uses FormData — do NOT set Content-Type manually. */
export async function resubmitInvoice(
  invoiceId: string,
  file: File,
): Promise<InvoiceUploadResponse> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${BASE_URL}/supplier/invoices/${invoiceId}/resubmit`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>;
    const detail =
      typeof body.detail === "string" ? body.detail : "Resubmission failed";
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<InvoiceUploadResponse>;
}

export function respondToException(
  exceptionId: string,
  supplierResponse: string,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(
    `/supplier/exceptions/${exceptionId}/respond`,
    {
      method: "POST",
      body: JSON.stringify({
        exception_id: exceptionId,
        supplier_response: supplierResponse,
      }),
    },
  );
}

// ── Carrier ───────────────────────────────────────────────────────────────────

export function listCarrierInvoices(
  statusFilter = "PENDING_CARRIER_REVIEW",
): Promise<InvoiceListItem[]> {
  return apiFetch<InvoiceListItem[]>(
    `/carrier/invoices?status_filter=${statusFilter}`,
  );
}

export function getCarrierInvoice(id: string): Promise<InvoiceDetail> {
  return apiFetch<InvoiceDetail>(`/carrier/invoices/${id}`);
}

export function getCarrierInvoiceLines(
  id: string,
): Promise<LineItemCarrierView[]> {
  return apiFetch<LineItemCarrierView[]>(`/carrier/invoices/${id}/lines`);
}

export function approveCarrierInvoice(
  id: string,
  notes?: string,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/carrier/invoices/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ notes: notes ?? null }),
  });
}

export function requestInvoiceChanges(
  id: string,
  carrierNotes: string,
): Promise<{ message: string; carrier_notes: string }> {
  return apiFetch<{ message: string; carrier_notes: string }>(
    `/carrier/invoices/${id}/request-changes`,
    {
      method: "POST",
      body: JSON.stringify({ carrier_notes: carrierNotes }),
    },
  );
}

export function resolveException(
  exceptionId: string,
  resolutionAction: string,
  resolutionNotes = "",
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(
    `/carrier/exceptions/${exceptionId}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({
        resolution_action: resolutionAction,
        resolution_notes: resolutionNotes,
      }),
    },
  );
}

/** Returns a Blob for client-side download. */
export async function exportCarrierInvoice(id: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}/carrier/invoices/${id}/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new ApiError(res.status, "Export failed");
  }
  return res.blob();
}

/** Helper: trigger browser download from a Blob. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Supplier — contracts ──────────────────────────────────────────────────────

export function listSupplierContracts(): Promise<
  {
    id: string;
    name: string;
    effective_from: string;
    effective_to: string | null;
    geography_scope: string;
  }[]
> {
  return apiFetch("/supplier/contracts");
}

// ── Admin (optional helpers for SYSTEM_ADMIN pages) ───────────────────────────

export function listAdminSuppliers(): Promise<AdminSupplier[]> {
  return apiFetch<AdminSupplier[]>("/admin/suppliers");
}

export function createAdminSupplier(payload: {
  name: string;
  tax_id?: string;
}): Promise<AdminSupplier> {
  return apiFetch<AdminSupplier>("/admin/suppliers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function listSupplierUsers(
  supplierId: string,
): Promise<{ id: string; email: string; is_active: boolean }[]> {
  return apiFetch(`/admin/suppliers/${supplierId}/users`);
}

export function createSupplierUser(
  supplierId: string,
  payload: { email: string; password: string },
): Promise<{ id: string; email: string; is_active: boolean }> {
  return apiFetch(`/admin/suppliers/${supplierId}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function listAdminContracts(supplierId?: string): Promise<AdminContract[]> {
  const qs = supplierId ? `?supplier_id=${supplierId}` : "";
  return apiFetch<AdminContract[]>(`/admin/contracts${qs}`);
}

export function getVerticals(): Promise<Vertical[]> {
  return apiFetch<Vertical[]>("/admin/verticals");
}

export function getAdminContract(id: string): Promise<ContractDetail> {
  return apiFetch<ContractDetail>(`/admin/contracts/${id}`);
}

export function createAdminContract(payload: ContractCreate): Promise<ContractDetail> {
  return apiFetch<ContractDetail>("/admin/contracts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createRateCard(contractId: string, payload: RateCardCreate): Promise<RateCardDetail> {
  return apiFetch<RateCardDetail>(`/admin/contracts/${contractId}/rate-cards`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteRateCard(contractId: string, rcId: string): Promise<void> {
  return apiFetch<void>(`/admin/contracts/${contractId}/rate-cards/${rcId}`, {
    method: "DELETE",
  });
}

export function createGuideline(contractId: string, payload: GuidelineCreate): Promise<GuidelineDetail> {
  return apiFetch<GuidelineDetail>(`/admin/contracts/${contractId}/guidelines`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateGuideline(
  contractId: string,
  gId: string,
  isActive: boolean,
): Promise<GuidelineDetail> {
  return apiFetch<GuidelineDetail>(
    `/admin/contracts/${contractId}/guidelines/${gId}?is_active=${isActive}`,
    { method: "PUT" },
  );
}

export function deleteGuideline(contractId: string, gId: string): Promise<void> {
  return apiFetch<void>(`/admin/contracts/${contractId}/guidelines/${gId}`, {
    method: "DELETE",
  });
}

export function getRateGaps(filters?: AnalyticsFilters): Promise<RateGap[]> {
  return apiFetch<RateGap[]>(`/admin/analytics/rate-gaps${_analyticsQs(filters)}`);
}

export async function parseContractPdf(
  supplierId: string,
  file: File,
): Promise<ParsedContractResult> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  form.append("supplier_id", supplierId);

  const res = await fetch(`${BASE_URL}/admin/contracts/parse-pdf`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Session expired — please log in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>;
    const detail = typeof body.detail === "string" ? body.detail : "PDF parsing failed";
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<ParsedContractResult>;
}

// ── Admin — invoices ──────────────────────────────────────────────────────────

/** List all invoices with optional search, supplier, date, and status filters. */
export function listAdminInvoices(filters: InvoiceListFilters = {}): Promise<InvoiceListItem[]> {
  const qs = new URLSearchParams();
  if (filters.statusFilter) qs.set("status_filter", filters.statusFilter);
  if (filters.search)       qs.set("search",         filters.search);
  if (filters.supplierId)   qs.set("supplier_id",     filters.supplierId);
  if (filters.dateFrom)     qs.set("date_from",        filters.dateFrom);
  if (filters.dateTo)       qs.set("date_to",          filters.dateTo);
  const q = qs.toString();
  return apiFetch<InvoiceListItem[]>(`/admin/invoices${q ? `?${q}` : ""}`);
}

/** Get a single invoice with supplier + contract name enrichment. */
export function getAdminInvoice(id: string): Promise<AdminInvoiceDetail> {
  return apiFetch<AdminInvoiceDetail>(`/admin/invoices/${id}`);
}

/** Get line items for an invoice (full carrier view with taxonomy). */
export function getAdminInvoiceLines(id: string): Promise<LineItemCarrierView[]> {
  return apiFetch<LineItemCarrierView[]>(`/admin/invoices/${id}/lines`);
}

/** Approve an invoice; optionally restrict to specific line IDs. */
export function approveAdminInvoice(
  id: string,
  lineItemIds?: string[],
  notes?: string,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/admin/invoices/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ line_item_ids: lineItemIds ?? null, notes: notes ?? null }),
  });
}

/** Bulk-resolve all open billing exceptions using their AI recommendation. */
export function acceptAiRecommendations(invoiceId: string): Promise<{
  accepted: number;
  skipped: number;
  invoice_status: string;
  message: string;
}> {
  return apiFetch(`/admin/invoices/${invoiceId}/accept-ai-recommendations`, {
    method: "POST",
  });
}

/** Approve multiple invoices at once. Invoices already approved are silently skipped. */
export function bulkApproveInvoices(
  invoiceIds: string[],
  notes?: string,
): Promise<BulkApprovalResult> {
  return apiFetch<BulkApprovalResult>("/admin/invoices/bulk-approve", {
    method: "POST",
    body: JSON.stringify({ invoice_ids: invoiceIds, notes: notes ?? null }),
  });
}

/** Export an approved invoice as a CSV blob. */
export async function exportAdminInvoice(id: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}/admin/invoices/${id}/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "Export failed");
  return res.blob();
}

/** Returns the URL to stream the original uploaded file (PDF opens inline, CSV downloads). */
export function originalInvoiceFileUrl(id: string): string {
  return `${BASE_URL}/admin/invoices/${id}/file`;
}

/** Fetches the original invoice file as a Blob (for CSV download). */
export async function downloadOriginalInvoiceFile(id: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}/admin/invoices/${id}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "File not available");
  return res.blob();
}

// ── Admin — exceptions ────────────────────────────────────────────────────────

/**
 * Admin exception resolution.
 * NOTE: backend reads these as query params (not JSON body).
 */
export function resolveAdminException(
  exceptionId: string,
  resolutionAction: string,
  resolutionNotes = "",
): Promise<{ message: string; invoice_status?: string; line_status?: string }> {
  const qs = new URLSearchParams({
    resolution_action: resolutionAction,
    resolution_notes: resolutionNotes,
  });
  return apiFetch<{ message: string }>(
    `/admin/exceptions/${exceptionId}/resolve?${qs}`,
    { method: "POST" },
  );
}

// ── Admin — mappings ──────────────────────────────────────────────────────────

export function getMappingReviewQueue(): Promise<MappingQueueItem[]> {
  return apiFetch<MappingQueueItem[]>("/admin/mappings/review-queue");
}

export function overrideMapping(
  lineItemId: string,
  taxonomyCode: string,
  billingComponent: string,
  scope: "this_line" | "this_supplier" | "global",
  notes?: string,
): Promise<{ message: string; scope: string; rule_created: boolean; rule_id: string | null }> {
  return apiFetch("/admin/mappings/override", {
    method: "POST",
    body: JSON.stringify({
      line_item_id: lineItemId,
      taxonomy_code: taxonomyCode,
      billing_component: billingComponent,
      scope,
      notes: notes ?? null,
    }),
  });
}

export function getGroupedReviewQueue(): Promise<ReviewQueueGroup[]> {
  return apiFetch<ReviewQueueGroup[]>("/admin/mappings/review-queue/grouped");
}

export function batchOverrideMapping(payload: {
  line_item_ids: string[];
  taxonomy_code: string;
  billing_component: string;
  scope: "this_line" | "this_supplier" | "global";
  notes?: string;
  is_confirm?: boolean;
}): Promise<{ updated: number; rules_created: number; skipped: number }> {
  return apiFetch("/admin/mappings/batch-override", {
    method: "POST",
    body: JSON.stringify({
      line_item_ids: payload.line_item_ids,
      taxonomy_code: payload.taxonomy_code,
      billing_component: payload.billing_component,
      scope: payload.scope,
      notes: payload.notes ?? null,
      is_confirm: payload.is_confirm ?? false,
    }),
  });
}

export function getMappingInsights(): Promise<MappingInsights> {
  return apiFetch<MappingInsights>("/admin/mappings/insights");
}

export function getExceptionDetails(
  exceptions: ExceptionView[],
): ExceptionView[] {
  return exceptions.filter((e) => e.status === "OPEN");
}

// ── Admin — analytics ─────────────────────────────────────────────────────────

/** Build a query-string from an AnalyticsFilters object. Returns "" if no filters. */
function _analyticsQs(filters?: AnalyticsFilters, extra?: Record<string, string>): string {
  const p = new URLSearchParams();
  if (filters?.date_from) p.set("date_from", filters.date_from);
  if (filters?.date_to) p.set("date_to", filters.date_to);
  if (filters?.supplier_id) p.set("supplier_id", filters.supplier_id);
  if (filters?.domain) p.set("domain", filters.domain);
  if (extra) Object.entries(extra).forEach(([k, v]) => p.set(k, v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function getAnalyticsSummary(filters?: AnalyticsFilters): Promise<AnalyticsSummary> {
  return apiFetch<AnalyticsSummary>(`/admin/analytics/summary${_analyticsQs(filters)}`);
}

export function getSpendByDomain(filters?: AnalyticsFilters): Promise<SpendByDomain[]> {
  return apiFetch<SpendByDomain[]>(`/admin/analytics/spend-by-domain${_analyticsQs(filters)}`);
}

export function getSpendBySupplier(filters?: AnalyticsFilters): Promise<SpendBySupplier[]> {
  return apiFetch<SpendBySupplier[]>(`/admin/analytics/spend-by-supplier${_analyticsQs(filters)}`);
}

export function getSpendByTaxonomy(filters?: AnalyticsFilters): Promise<SpendByTaxonomy[]> {
  return apiFetch<SpendByTaxonomy[]>(`/admin/analytics/spend-by-taxonomy${_analyticsQs(filters)}`);
}

export function getExceptionBreakdown(filters?: AnalyticsFilters): Promise<ExceptionBreakdown[]> {
  return apiFetch<ExceptionBreakdown[]>(`/admin/analytics/exception-breakdown${_analyticsQs(filters)}`);
}

export function getSupplierComparison(filters?: AnalyticsFilters): Promise<SupplierComparisonRow[]> {
  return apiFetch<SupplierComparisonRow[]>(`/admin/analytics/supplier-comparison${_analyticsQs(filters)}`);
}

export function getAiAccuracy(): Promise<AiAccuracyStats> {
  return apiFetch<AiAccuracyStats>("/admin/analytics/ai-accuracy");
}

/** Run an AI audit on a supplier — returns findings and risk rating. No DB writes. */
export function runSupplierAudit(supplierId: string): Promise<SupplierAuditResult> {
  return apiFetch<SupplierAuditResult>(`/admin/suppliers/${supplierId}/audit`, {
    method: "POST",
  });
}

// ── Admin — Supplier Profile ──────────────────────────────────────────────────

export function getSupplierProfile(supplierId: string): Promise<SupplierProfile> {
  return apiFetch<SupplierProfile>(`/admin/suppliers/${supplierId}/profile`);
}

export function updateSupplierProfile(
  supplierId: string,
  payload: SupplierProfileUpdate,
): Promise<SupplierProfile> {
  return apiFetch<SupplierProfile>(`/admin/suppliers/${supplierId}/profile`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ── Admin — Supplier State Machine ────────────────────────────────────────────

export function submitSupplierForReview(
  supplierId: string,
): Promise<{ message: string; status: string }> {
  return apiFetch(`/admin/suppliers/${supplierId}/submit`, { method: "POST" });
}

export function approveSupplier(
  supplierId: string,
): Promise<{ message: string; status: string }> {
  return apiFetch(`/admin/suppliers/${supplierId}/approve`, { method: "POST" });
}

export function rejectSupplier(
  supplierId: string,
  notes?: string,
): Promise<{ message: string; status: string }> {
  const qs = notes ? `?notes=${encodeURIComponent(notes)}` : "";
  return apiFetch(`/admin/suppliers/${supplierId}/reject${qs}`, { method: "POST" });
}

export function suspendSupplier(
  supplierId: string,
  notes?: string,
): Promise<{ message: string; status: string }> {
  const qs = notes ? `?notes=${encodeURIComponent(notes)}` : "";
  return apiFetch(`/admin/suppliers/${supplierId}/suspend${qs}`, { method: "POST" });
}

export function reinstateSupplier(
  supplierId: string,
): Promise<{ message: string; status: string }> {
  return apiFetch(`/admin/suppliers/${supplierId}/reinstate`, { method: "POST" });
}

// ── Admin — Supplier Documents ────────────────────────────────────────────────

export function listSupplierDocuments(supplierId: string): Promise<SupplierDocument[]> {
  return apiFetch<SupplierDocument[]>(`/admin/suppliers/${supplierId}/documents`);
}

export async function uploadSupplierDocument(
  supplierId: string,
  documentType: "W9" | "COI" | "MSA" | "OTHER",
  file: File,
  expiresAt?: string,
  notes?: string,
): Promise<SupplierDocument> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  form.append("document_type", documentType);
  if (expiresAt) form.append("expires_at", expiresAt);
  if (notes) form.append("notes", notes);

  const res = await fetch(`${BASE_URL}/admin/suppliers/${supplierId}/documents`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Session expired — please log in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>;
    const detail = typeof body.detail === "string" ? body.detail : "Upload failed";
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<SupplierDocument>;
}

// ── Admin — Taxonomy Import ───────────────────────────────────────────────────

export async function importSupplierTaxonomy(
  supplierId: string,
  file: File,
): Promise<TaxonomyImportResult> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(
    `${BASE_URL}/admin/suppliers/${supplierId}/taxonomy-import`,
    {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    },
  );

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Session expired — please log in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>;
    const detail = typeof body.detail === "string" ? body.detail : "Import failed";
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<TaxonomyImportResult>;
}

/** Fetch the supplier comparison as a CSV blob for download. */
export async function getSupplierComparisonCsv(filters?: AnalyticsFilters): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = { Accept: "text/csv" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const qs = _analyticsQs(filters, { format: "csv" });
  const res = await fetch(`${BASE_URL}/admin/analytics/supplier-comparison${qs}`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

// ── Admin — Geographic analytics ─────────────────────────────────────────────

export function getSpendByState(filters?: AnalyticsFilters): Promise<SpendByState[]> {
  return apiFetch<SpendByState[]>(`/admin/analytics/spend-by-state${_analyticsQs(filters)}`);
}

export function getSpendByZip(state?: string, filters?: AnalyticsFilters): Promise<SpendByZip[]> {
  const extra: Record<string, string> = {};
  if (state) extra["state"] = state;
  return apiFetch<SpendByZip[]>(`/admin/analytics/spend-by-zip${_analyticsQs(filters, extra)}`);
}

export function getSpendTrend(period: "month" | "week" = "month", filters?: AnalyticsFilters): Promise<SpendTrend[]> {
  return apiFetch<SpendTrend[]>(`/admin/analytics/spend-trend${_analyticsQs(filters, { period })}`);
}

export function getContractHealth(): Promise<ContractHealth[]> {
  return apiFetch<ContractHealth[]>("/admin/analytics/contract-health");
}

export function getSupplierScorecard(supplierId: string): Promise<SupplierScorecard> {
  return apiFetch<SupplierScorecard>(`/admin/analytics/supplier-scorecard/${supplierId}`);
}

// ── New demand / spend intelligence endpoints ──────────────────────────────────

export function getSavingsRealization(filters?: AnalyticsFilters): Promise<SavingsRealization> {
  return apiFetch<SavingsRealization>(`/admin/analytics/savings-realization${_analyticsQs(filters)}`);
}

export function getUtilization(filters?: AnalyticsFilters): Promise<UtilizationRow[]> {
  return apiFetch<UtilizationRow[]>(`/admin/analytics/utilization${_analyticsQs(filters)}`);
}

export function getClaimStacking(filters?: AnalyticsFilters): Promise<ClaimStackingRow[]> {
  return apiFetch<ClaimStackingRow[]>(`/admin/analytics/claim-stacking${_analyticsQs(filters)}`);
}

export function getRateBenchmarks(filters?: AnalyticsFilters): Promise<RateBenchmarkRow[]> {
  return apiFetch<RateBenchmarkRow[]>(`/admin/analytics/rate-benchmarks${_analyticsQs(filters)}`);
}

export function getValueSummary(filters?: Pick<AnalyticsFilters, "date_from" | "date_to">): Promise<ValueSummary> {
  const params = new URLSearchParams();
  if (filters?.date_from) params.set("date_from", filters.date_from);
  if (filters?.date_to) params.set("date_to", filters.date_to);
  const qs = params.toString();
  return apiFetch<ValueSummary>(`/admin/analytics/value-summary${qs ? `?${qs}` : ""}`);
}

// ── Admin — Carrier Team ──────────────────────────────────────────────────────

export function listCarrierUsers(): Promise<CarrierUser[]> {
  return apiFetch<CarrierUser[]>("/admin/users");
}

export function createCarrierUser(payload: CarrierUserCreate): Promise<CarrierUser> {
  return apiFetch<CarrierUser>("/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateUserScope(
  userId: string,
  payload: UserScopeUpdate,
): Promise<CarrierUser> {
  return apiFetch<CarrierUser>(`/admin/users/${userId}/scope`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ── Seed Demo ─────────────────────────────────────────────────────────────────

/** Enqueue the synthetic data seeder. Returns {job_id, status: "queued"}. */
export function runSeedDemo(clean: boolean): Promise<{ job_id: string; status: string }> {
  return apiFetch<{ job_id: string; status: string }>(
    `/admin/seed-demo?clean=${clean}`,
    { method: "POST" },
  );
}

/** Poll seed job status. */
export function getSeedDemoStatus(jobId: string): Promise<SeedDemoJobStatus> {
  return apiFetch<SeedDemoJobStatus>(`/admin/seed-demo/${jobId}`);
}

// ── Carrier Settings ──────────────────────────────────────────────────────────

/** Fetch the current per-carrier pipeline and processing settings. */
export function getCarrierSettings(): Promise<CarrierSettings> {
  return apiFetch<CarrierSettings>("/admin/carriers/settings");
}

/** Replace carrier settings (full replace, not patch). */
export function updateCarrierSettings(
  payload: CarrierSettings,
): Promise<CarrierSettings> {
  return apiFetch<CarrierSettings>("/admin/carriers/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

// ── Classification Review ──────────────────────────────────────────────────────

/**
 * List classification queue items for this carrier.
 * statusFilter: "PENDING" | "NEEDS_REVIEW" | "APPROVED" | "REJECTED"
 */
export function listClassificationQueue(
  statusFilter: string = "PENDING",
  invoiceId?: string,
): Promise<ClassificationQueueItem[]> {
  const params = new URLSearchParams({ status_filter: statusFilter });
  if (invoiceId) params.set("invoice_id", invoiceId);
  return apiFetch<ClassificationQueueItem[]>(
    `/carrier/classification?${params.toString()}`,
  );
}

/** Summary stats for the Classification Review screen header. */
export function getClassificationStats(): Promise<ClassificationStats> {
  return apiFetch<ClassificationStats>("/carrier/classification/stats");
}

/** Bulk-approve classification items using their AI proposed code. Skips items with no proposal. */
export function bulkApproveClassificationItems(
  itemIds: string[],
): Promise<{ approved: number; skipped: number; bill_audit_exceptions: number }> {
  return apiFetch("/carrier/classification/bulk-approve", {
    method: "POST",
    body: JSON.stringify(itemIds),
  });
}

/** Approve a classification queue item (confirm taxonomy + run bill audit). */
export function approveClassificationItem(
  itemId: string,
  payload: ClassificationApproveRequest,
): Promise<ClassificationApproveResult> {
  return apiFetch<ClassificationApproveResult>(
    `/carrier/classification/${itemId}/approve`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

/** Reject a classification queue item (marks line as DENIED). */
export function rejectClassificationItem(
  itemId: string,
  payload: ClassificationRejectRequest,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(
    `/carrier/classification/${itemId}/reject`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}
