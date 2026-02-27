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
  ExceptionView,
  InvoiceCreate,
  InvoiceDetail,
  InvoiceListItem,
  InvoiceUploadResponse,
  LineItemCarrierView,
  LineItemSupplierView,
  MappingQueueItem,
  TokenResponse,
  UserInfo,
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

export function listAdminContracts(supplierId?: string): Promise<AdminContract[]> {
  const qs = supplierId ? `?supplier_id=${supplierId}` : "";
  return apiFetch<AdminContract[]>(`/admin/contracts${qs}`);
}

// ── Admin — invoices ──────────────────────────────────────────────────────────

/** List all invoices, optionally filtered by status. Omit statusFilter to get all. */
export function listAdminInvoices(statusFilter?: string): Promise<InvoiceListItem[]> {
  const qs = statusFilter ? `?status_filter=${statusFilter}` : "";
  return apiFetch<InvoiceListItem[]>(`/admin/invoices${qs}`);
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

/** Export an approved invoice as a CSV blob. */
export async function exportAdminInvoice(id: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}/admin/invoices/${id}/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "Export failed");
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
): Promise<{ message: string }> {
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

export function getExceptionDetails(
  exceptions: ExceptionView[],
): ExceptionView[] {
  return exceptions.filter((e) => e.status === "OPEN");
}
