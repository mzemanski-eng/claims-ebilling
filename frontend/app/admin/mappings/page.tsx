"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getMappingReviewQueue, overrideMapping } from "@/lib/api";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { Button } from "@/components/ui/button";
import type { MappingQueueItem } from "@/lib/types";

type Scope = "this_line" | "this_supplier" | "global";

function OverrideForm({
  item,
  onDone,
}: {
  item: MappingQueueItem;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [taxonomyCode, setTaxonomyCode] = useState(item.taxonomy_code ?? "");
  const [billingComponent, setBillingComponent] = useState(
    item.billing_component ?? "",
  );
  const [scope, setScope] = useState<Scope>("this_supplier");
  const [notes, setNotes] = useState("");

  const mut = useMutation({
    mutationFn: () =>
      overrideMapping(
        item.line_item_id,
        taxonomyCode,
        billingComponent,
        scope,
        notes || undefined,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mapping-queue"] });
      onDone();
    },
  });

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
      <h4 className="text-xs font-semibold uppercase text-blue-700">
        Override Mapping
      </h4>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-gray-600">
            Taxonomy Code
          </label>
          <input
            type="text"
            value={taxonomyCode}
            onChange={(e) => setTaxonomyCode(e.target.value)}
            placeholder="e.g. IME.PHY_EXAM.PROF_FEE"
            className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600">
            Billing Component
          </label>
          <input
            type="text"
            value={billingComponent}
            onChange={(e) => setBillingComponent(e.target.value)}
            placeholder="e.g. PROF_FEE"
            className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-gray-600">
            Save as rule for
          </label>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as Scope)}
            className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="this_line">This line only</option>
            <option value="this_supplier">This supplier (creates rule)</option>
            <option value="global">All suppliers (global rule)</option>
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600">
            Notes (optional)
          </label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Reason for override…"
            className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      </div>
      {mut.isError && (
        <p className="text-xs text-red-600">{(mut.error as Error).message}</p>
      )}
      {mut.isSuccess && (
        <p className="text-xs text-green-700">
          ✓ Mapping updated
          {mut.data.rule_created ? " — rule saved" : ""}.
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <Button
          size="sm"
          loading={mut.isPending}
          disabled={!taxonomyCode || !billingComponent}
          onClick={() => mut.mutate()}
        >
          Save Override
        </Button>
      </div>
    </div>
  );
}

export default function AdminMappingsPage() {
  const [expandedItem, setExpandedItem] = useState<string | null>(null);

  const { data: items, isLoading } = useQuery({
    queryKey: ["mapping-queue"],
    queryFn: getMappingReviewQueue,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Mapping Queue</h1>
          <p className="mt-1 text-sm text-gray-500">
            {items?.length ?? 0} lines with LOW or MEDIUM mapping confidence
          </p>
        </div>
        <Link
          href="/admin/invoices"
          className="text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          ← Invoice Queue
        </Link>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      ) : items?.length === 0 ? (
        <div className="rounded-xl border bg-white py-16 text-center text-sm text-gray-400 shadow-sm">
          No low-confidence mappings. The classifier is doing well!
        </div>
      ) : (
        <div className="space-y-3">
          {items?.map((item) => (
            <div
              key={item.line_item_id}
              className="rounded-xl border bg-white p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <ConfidenceBadge confidence={item.mapping_confidence} />
                    <Link
                      href={`/admin/invoices/${item.invoice_id}`}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Invoice #{item.invoice_id.slice(0, 8)}…
                    </Link>
                    <span className="text-xs text-gray-400">
                      Line {item.line_number}
                    </span>
                  </div>
                  <p className="mt-2 text-sm font-medium text-gray-900">
                    {item.raw_description}
                  </p>
                  <div className="mt-1 flex items-center gap-4 text-xs text-gray-500">
                    {item.taxonomy_code ? (
                      <span className="font-mono">{item.taxonomy_code}</span>
                    ) : (
                      <span className="italic text-gray-300">
                        No taxonomy assigned
                      </span>
                    )}
                    <span className="font-mono text-gray-700">
                      ${Number(item.raw_amount).toFixed(2)}
                    </span>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setExpandedItem(
                      expandedItem === item.line_item_id
                        ? null
                        : item.line_item_id,
                    )
                  }
                >
                  {expandedItem === item.line_item_id ? "Cancel" : "Override"}
                </Button>
              </div>

              {expandedItem === item.line_item_id && (
                <OverrideForm
                  item={item}
                  onDone={() => setExpandedItem(null)}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
