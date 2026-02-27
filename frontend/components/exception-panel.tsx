"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { resolveException, respondToException } from "@/lib/api";
import { isCarrierAdmin } from "@/lib/auth";
import type { ExceptionView } from "@/lib/types";
import { ResolutionActions } from "@/lib/types";
import { StatusBadge } from "./status-badge";
import { Button } from "./ui/button";
import { Select } from "./ui/select";
import { Textarea } from "./ui/textarea";

const RESOLUTION_OPTIONS = [
  { value: ResolutionActions.HELD_CONTRACT_RATE, label: "Hold Contract Rate" },
  { value: ResolutionActions.WAIVED, label: "Waive Exception" },
  { value: ResolutionActions.RECLASSIFIED, label: "Reclassify Line" },
  { value: ResolutionActions.ACCEPTED_REDUCTION, label: "Accept Reduction" },
  { value: ResolutionActions.DENIED, label: "Deny Line" },
];

// Plain-English carrier decision labels shown to suppliers once an exception is resolved
const RESOLUTION_LABELS: Record<
  string,
  { icon: string; label: string; colorClasses: string }
> = {
  DENIED: {
    icon: "🚫",
    label:
      "Not approved — the carrier has denied this line. It will not be included in your payment.",
    colorClasses: "border-red-200 bg-red-50 text-red-800",
  },
  WAIVED: {
    icon: "✓",
    label:
      "Exception waived — the carrier has accepted this charge despite the exception.",
    colorClasses: "border-green-200 bg-green-50 text-green-800",
  },
  HELD_CONTRACT_RATE: {
    icon: "↓",
    label:
      "Contract rate applied — the carrier will pay at the contracted rate, not the billed amount.",
    colorClasses: "border-yellow-200 bg-yellow-50 text-yellow-800",
  },
  ACCEPTED_REDUCTION: {
    icon: "✓",
    label:
      "Reduction accepted — the carrier has accepted this line at a reduced amount.",
    colorClasses: "border-green-200 bg-green-50 text-green-800",
  },
  RECLASSIFIED: {
    icon: "↔",
    label:
      "Reclassified by carrier — this line has been assigned a different billing category.",
    colorClasses: "border-blue-200 bg-blue-50 text-blue-800",
  },
};

// ── Carrier exception resolution ──────────────────────────────────────────────

interface CarrierExceptionCardProps {
  exception: ExceptionView;
  invoiceId: string;
}

function CarrierExceptionCard({
  exception,
  invoiceId,
}: CarrierExceptionCardProps) {
  const [action, setAction] = useState<string>(ResolutionActions.HELD_CONTRACT_RATE);
  const [notes, setNotes] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => resolveException(exception.exception_id, action, notes),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["carrier-lines", invoiceId] });
      void queryClient.invalidateQueries({ queryKey: ["carrier-invoice", invoiceId] });
    },
  });

  const isResolved =
    exception.status === "RESOLVED" || exception.status === "WAIVED";

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={exception.status} />
            <span className="text-xs text-gray-500">
              {exception.severity} · {exception.required_action.replace(/_/g, " ")}
            </span>
          </div>
          <p className="mt-1 text-sm font-medium text-gray-800">
            {exception.message}
          </p>
          {exception.supplier_response && (
            <div className="mt-2 rounded border-l-4 border-blue-300 bg-blue-50 px-3 py-2">
              <p className="text-xs font-medium text-blue-700">
                Supplier response:
              </p>
              <p className="text-sm text-blue-800">
                {exception.supplier_response}
              </p>
            </div>
          )}
        </div>
      </div>

      {!isResolved && isCarrierAdmin() && (
        <div className="mt-3 flex flex-col gap-2 border-t border-red-200 pt-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Select
              label="Resolution"
              id={`action-${exception.exception_id}`}
              options={RESOLUTION_OPTIONS}
              value={action}
              onChange={(e) => setAction(e.target.value)}
            />
          </div>
          <div className="flex-1">
            <Textarea
              label="Notes (optional)"
              id={`notes-${exception.exception_id}`}
              placeholder="Add resolution notes…"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={mutation.isPending}
          >
            Resolve
          </Button>
        </div>
      )}

      {mutation.isError && (
        <p className="mt-2 text-xs text-red-600">
          {(mutation.error as Error).message}
        </p>
      )}
    </div>
  );
}

// ── Supplier exception response ───────────────────────────────────────────────

interface SupplierExceptionCardProps {
  exception: ExceptionView;
  invoiceId: string;
}

function SupplierExceptionCard({
  exception,
  invoiceId,
}: SupplierExceptionCardProps) {
  const [response, setResponse] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => respondToException(exception.exception_id, response),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["supplier-lines", invoiceId] });
      void queryClient.invalidateQueries({ queryKey: ["supplier-invoice", invoiceId] });
    },
  });

  const isOpen = exception.status === "OPEN";
  const hasResolution = !!exception.resolution_action;
  const resolutionInfo = exception.resolution_action
    ? RESOLUTION_LABELS[exception.resolution_action]
    : null;

  return (
    <div className="rounded-lg border border-orange-200 bg-orange-50 p-4">
      {/* Carrier decision banner — shown prominently once the carrier has resolved */}
      {hasResolution && resolutionInfo && (
        <div
          className={`mb-3 rounded-md border px-3 py-2 text-sm font-medium ${resolutionInfo.colorClasses}`}
        >
          <span className="mr-1.5">{resolutionInfo.icon}</span>
          {resolutionInfo.label}
        </div>
      )}

      <div className="flex items-center gap-2">
        <StatusBadge status={exception.status} />
        <span className="text-xs text-gray-500">
          {exception.severity} · {exception.required_action.replace(/_/g, " ")}
        </span>
      </div>
      <p className="mt-1 text-sm font-medium text-gray-800">
        {exception.message}
      </p>

      {exception.supplier_response && (
        <p className="mt-2 text-sm text-gray-600 italic">
          Your response: {exception.supplier_response}
        </p>
      )}

      {/* Response textarea — hidden when the carrier has already resolved this exception */}
      {isOpen && !hasResolution && (
        <div className="mt-3 flex flex-col gap-2 border-t border-orange-200 pt-3 sm:flex-row sm:items-end">
          <Textarea
            className="flex-1"
            id={`resp-${exception.exception_id}`}
            placeholder="Explain the discrepancy or dispute the exception…"
            rows={2}
            value={response}
            onChange={(e) => setResponse(e.target.value)}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={mutation.isPending || !response.trim()}
          >
            Send Response
          </Button>
        </div>
      )}

      {mutation.isError && (
        <p className="mt-2 text-xs text-red-600">
          {(mutation.error as Error).message}
        </p>
      )}
    </div>
  );
}

// ── Public panel exports ───────────────────────────────────────────────────────

export function CarrierExceptionPanel({
  exceptions,
  invoiceId,
}: {
  exceptions: ExceptionView[];
  invoiceId: string;
}) {
  const open = exceptions.filter((e) => e.status === "OPEN" || e.status === "SUPPLIER_RESPONDED");
  const resolved = exceptions.filter(
    (e) => e.status === "RESOLVED" || e.status === "WAIVED",
  );

  if (exceptions.length === 0)
    return (
      <p className="text-sm text-gray-500 py-2">No exceptions on this line.</p>
    );

  return (
    <div className="space-y-3">
      {open.map((e) => (
        <CarrierExceptionCard
          key={e.exception_id}
          exception={e}
          invoiceId={invoiceId}
        />
      ))}
      {resolved.map((e) => (
        <div
          key={e.exception_id}
          className="rounded-lg border border-gray-200 bg-white p-3 opacity-60"
        >
          <div className="flex items-center gap-2">
            <StatusBadge status={e.status} />
            <span className="text-xs text-gray-500">{e.message}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function SupplierExceptionPanel({
  exceptions,
  invoiceId,
}: {
  exceptions: ExceptionView[];
  invoiceId: string;
}) {
  if (exceptions.length === 0) return null;
  return (
    <div className="space-y-2">
      {exceptions.map((e) => (
        <SupplierExceptionCard
          key={e.exception_id}
          exception={e}
          invoiceId={invoiceId}
        />
      ))}
    </div>
  );
}
