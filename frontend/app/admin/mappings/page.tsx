"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getGroupedReviewQueue,
  batchOverrideMapping,
  getMappingInsights,
  overrideMapping,
} from "@/lib/api";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/toast";
import type { MappingQueueItem, ReviewQueueGroup, MappingInsightSuggestion } from "@/lib/types";

type Scope = "this_line" | "this_supplier" | "global";

type SingleResult = {
  message: string;
  scope: string;
  rule_created: boolean;
  rule_id: string | null;
};
type BatchResult = { updated: number; rules_created: number; skipped: number };
type OverrideResult = SingleResult | BatchResult;

function isBatchResult(r: OverrideResult): r is BatchResult {
  return "updated" in r;
}

// ── Override form (single item OR all items in a group) ──────────────────────

function OverrideForm({
  item,
  lineItemIds,
  initialTaxonomy,
  initialComponent,
  onDone,
}: {
  item: MappingQueueItem;
  lineItemIds?: string[]; // if set, batch-override all; otherwise single item
  initialTaxonomy?: string;
  initialComponent?: string;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const isBatch = lineItemIds && lineItemIds.length > 1;

  const [taxonomyCode, setTaxonomyCode] = useState(
    initialTaxonomy ?? item.taxonomy_code ?? "",
  );
  const [billingComponent, setBillingComponent] = useState(
    initialComponent ?? item.billing_component ?? "",
  );
  const [scope, setScope] = useState<Scope>("this_supplier");
  const [notes, setNotes] = useState("");

  const mut = useMutation<OverrideResult>({
    mutationFn: () => {
      const ids = lineItemIds ?? [item.line_item_id];
      if (ids.length > 1) {
        return batchOverrideMapping({
          line_item_ids: ids,
          taxonomy_code: taxonomyCode,
          billing_component: billingComponent,
          scope,
          notes: notes || undefined,
          is_confirm: false,
        });
      }
      return overrideMapping(
        item.line_item_id,
        taxonomyCode,
        billingComponent,
        scope,
        notes || undefined,
      );
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["mapping-queue-grouped"] });
      qc.invalidateQueries({ queryKey: ["mapping-insights"] });
      if (isBatchResult(data)) {
        const ruleMsg = data.rules_created
          ? ` · ${data.rules_created} rule${data.rules_created !== 1 ? "s" : ""} saved`
          : "";
        toast.success(`${data.updated} lines updated${ruleMsg}`);
      } else {
        toast.success(
          "Mapping updated",
          data.rule_created ? "Rule saved — future similar lines will classify automatically." : undefined,
        );
      }
      onDone();
    },
    onError: (err: Error) => toast.error("Could not update mapping", err.message),
  });

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
      <h4 className="text-xs font-semibold uppercase text-blue-700">
        {isBatch ? `Override ${lineItemIds!.length} Lines` : "Override Mapping"}
      </h4>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-gray-600">Taxonomy Code</label>
          <input
            type="text"
            value={taxonomyCode}
            onChange={(e) => setTaxonomyCode(e.target.value)}
            placeholder="e.g. IA.FIELD_ASSIGN.PROF_FEE"
            className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600">Billing Component</label>
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
          <label className="text-xs font-medium text-gray-600">Save as rule for</label>
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
          <label className="text-xs font-medium text-gray-600">Notes (optional)</label>
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
        <p className="text-xs text-red-600">
          {(mut.error as Error).message}{" "}
          <button className="underline hover:no-underline" onClick={() => mut.mutate()}>
            Retry
          </button>
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <Button
          size="sm"
          loading={mut.isPending}
          disabled={!taxonomyCode.trim() || !billingComponent.trim()}
          onClick={() => mut.mutate()}
        >
          Save Override
        </Button>
      </div>
    </div>
  );
}

// ── Individual item row (inside expanded group) ───────────────────────────────

function GroupItem({
  item,
  isOverriding,
  onToggleOverride,
}: {
  item: MappingQueueItem;
  isOverriding: boolean;
  onToggleOverride: () => void;
}) {
  return (
    <div className="px-5 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Link
              href={`/admin/invoices/${item.invoice_id}`}
              className="text-blue-600 hover:underline"
            >
              Invoice #{item.invoice_id.slice(0, 8)}…
            </Link>
            <span>Line {item.line_number}</span>
            <span className="font-mono text-gray-700">
              ${Number(item.raw_amount).toFixed(2)}
            </span>
            {item.mapping_confidence && <ConfidenceBadge confidence={item.mapping_confidence} />}
          </div>
          <p className="mt-0.5 text-sm text-gray-800">{item.raw_description}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={onToggleOverride}>
          {isOverriding ? "Cancel" : "Override"}
        </Button>
      </div>
      {isOverriding && (
        <OverrideForm
          item={item}
          initialTaxonomy={
            item.ai_classification_suggestion?.suggested_code ?? item.taxonomy_code ?? ""
          }
          initialComponent={
            item.ai_classification_suggestion?.suggested_billing_component ??
            item.billing_component ??
            ""
          }
          onDone={onToggleOverride}
        />
      )}
    </div>
  );
}

// ── Group card ────────────────────────────────────────────────────────────────

function GroupCard({
  group,
  isExpanded,
  onToggleExpand,
  isOverridingGroup,
  onToggleGroupOverride,
  overrideItemId,
  onToggleItemOverride,
  onConfirmAll,
  confirmPending,
}: {
  group: ReviewQueueGroup;
  isExpanded: boolean;
  onToggleExpand: () => void;
  isOverridingGroup: boolean;
  onToggleGroupOverride: () => void;
  overrideItemId: string | null;
  onToggleItemOverride: (id: string) => void;
  onConfirmAll: () => void;
  confirmPending: boolean;
}) {
  const canConfirmAll =
    group.suggested_taxonomy_code !== null && group.suggested_billing_component !== null;

  return (
    <div className="rounded-xl border bg-white shadow-sm">
      <div className="p-5">
        {/* Group header row */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-gray-900">{group.supplier_name}</span>
              {group.suggested_taxonomy_code ? (
                <span className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-xs text-blue-700">
                  {group.suggested_taxonomy_code}
                </span>
              ) : (
                <span className="text-xs italic text-gray-400">Unclassified</span>
              )}
              {group.confidence && <ConfidenceBadge confidence={group.confidence} />}
              <span className="text-xs text-gray-400">
                {group.item_count} line{group.item_count !== 1 ? "s" : ""}
                {" · "}$
                {Number(group.total_amount).toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
            </div>
            {/* Sample descriptions */}
            <div className="mt-2 space-y-0.5">
              {group.sample_descriptions.map((desc, i) => (
                <p key={i} className="truncate text-sm text-gray-600">
                  {desc}
                </p>
              ))}
              {group.item_count > group.sample_descriptions.length && (
                <p className="text-xs text-gray-400">
                  +{group.item_count - group.sample_descriptions.length} more
                </p>
              )}
            </div>
          </div>

          {/* Action buttons — Confirm All is primary; Override All is low-emphasis */}
          <div className="flex shrink-0 items-center gap-3">
            {canConfirmAll && (
              <Button
                size="sm"
                loading={confirmPending}
                disabled={confirmPending}
                className="!bg-green-600 !text-white hover:!bg-green-700 disabled:!bg-green-300"
                onClick={onConfirmAll}
              >
                ✓ Confirm All
              </Button>
            )}
            <button
              onClick={onToggleGroupOverride}
              className="text-xs text-gray-400 hover:text-gray-700 transition-colors underline underline-offset-2"
            >
              {isOverridingGroup ? "Cancel" : "Override All"}
            </button>
          </div>
        </div>

        {/* Group-level override form */}
        {isOverridingGroup && group.items.length > 0 && (
          <OverrideForm
            item={group.items[0]}
            lineItemIds={group.line_item_ids}
            initialTaxonomy={
              group.suggested_taxonomy_code ?? group.items[0].taxonomy_code ?? ""
            }
            initialComponent={
              group.suggested_billing_component ?? group.items[0].billing_component ?? ""
            }
            onDone={onToggleGroupOverride}
          />
        )}

        {/* Expand toggle (only shown for multi-item groups) */}
        {group.item_count > 1 && (
          <button
            className="mt-3 flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
            onClick={onToggleExpand}
          >
            <span>{isExpanded ? "▾" : "▸"}</span>
            <span>
              {isExpanded ? "Hide" : "Show"} {group.item_count} items
            </span>
          </button>
        )}
      </div>

      {/* Expanded individual items */}
      {isExpanded && (
        <div className="divide-y border-t">
          {group.items.map((item) => (
            <GroupItem
              key={item.line_item_id}
              item={item}
              isOverriding={overrideItemId === item.line_item_id}
              onToggleOverride={() => onToggleItemOverride(item.line_item_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminMappingsPage() {
  const qc = useQueryClient();
  const toast = useToast();

  // Smart back-navigation: return to the originating invoice if we came from one
  const [backUrl, setBackUrl] = useState("/admin/invoices");
  useEffect(() => {
    try {
      const ref = document.referrer;
      if (ref && new URL(ref).pathname.match(/^\/admin\/invoices\/[^/]+$/)) {
        setBackUrl(new URL(ref).pathname);
      }
    } catch {}
  }, []);

  // Track which group key is currently being confirmed, so only that card shows loading
  const [pendingGroupKey, setPendingGroupKey] = useState<string | null>(null);

  // Insights: dismissed suggestion IDs persisted to localStorage
  const [dismissedSuggestions, setDismissedSuggestions] = useState<Set<string>>(() => {
    if (typeof window === "undefined") return new Set();
    try {
      return new Set<string>(
        JSON.parse(localStorage.getItem("mq-dismissed-suggestions") || "[]"),
      );
    } catch {
      return new Set();
    }
  });

  // UI state: which group is expanded, has override form open, or item-level override
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [overrideGroupKey, setOverrideGroupKey] = useState<string | null>(null);
  const [overrideItemId, setOverrideItemId] = useState<string | null>(null);

  const { data: groups, isLoading } = useQuery({
    queryKey: ["mapping-queue-grouped"],
    queryFn: getGroupedReviewQueue,
  });

  const { data: insights } = useQuery({
    queryKey: ["mapping-insights"],
    queryFn: getMappingInsights,
  });

  // Shared batch-confirm mutation (used by "Confirm All" cards and insight suggestions)
  const batchConfirmMut = useMutation({
    mutationFn: (vars: {
      line_item_ids: string[];
      taxonomy_code: string;
      billing_component: string;
    }) =>
      batchOverrideMapping({
        ...vars,
        scope: "this_supplier",
        is_confirm: true,
      }),
    onSuccess: (data) => {
      setPendingGroupKey(null);
      qc.invalidateQueries({ queryKey: ["mapping-queue-grouped"] });
      qc.invalidateQueries({ queryKey: ["mapping-insights"] });
      const ruleMsg = data.rules_created
        ? `${data.rules_created} rule${data.rules_created !== 1 ? "s" : ""} saved — future similar lines will classify automatically.`
        : undefined;
      toast.success(
        `${data.updated} line${data.updated !== 1 ? "s" : ""} confirmed`,
        ruleMsg,
      );
    },
    onError: (err: Error) => {
      setPendingGroupKey(null);
      toast.error("Could not confirm", err.message);
    },
  });

  function toggleGroup(groupKey: string) {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      next.has(groupKey) ? next.delete(groupKey) : next.add(groupKey);
      return next;
    });
  }

  function toggleGroupOverride(groupKey: string) {
    setOverrideGroupKey((prev) => (prev === groupKey ? null : groupKey));
    setOverrideItemId(null);
  }

  function toggleItemOverride(itemId: string) {
    setOverrideItemId((prev) => (prev === itemId ? null : itemId));
    setOverrideGroupKey(null);
  }

  function dismissSuggestion(id: string) {
    setDismissedSuggestions((prev) => {
      const next = new Set(prev);
      next.add(id);
      try {
        localStorage.setItem("mq-dismissed-suggestions", JSON.stringify([...next]));
      } catch {}
      return next;
    });
  }

  const visibleSuggestions = (insights?.suggestions ?? []).filter(
    (s) => !dismissedSuggestions.has(s.id),
  );

  const totalCount = groups?.reduce((sum, g) => sum + g.item_count, 0) ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Classification Review</h1>
          <p className="mt-1 text-sm text-gray-500">
            Review AI spend-bucket assignments for unrecognized or uncertain service codes.
          </p>
          {insights ? (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-500">
              <span>
                <span className="font-semibold text-gray-900">{insights.stats.queue_count}</span>
                {" "}in queue
              </span>
              <span className="text-gray-300">·</span>
              <span>
                <span className="font-semibold text-gray-900">
                  {insights.stats.rules_learned_30d}
                </span>
                {" "}rules learned (30d)
              </span>
              {visibleSuggestions.length > 0 && (
                <>
                  <span className="text-gray-300">·</span>
                  <span className="font-medium text-amber-600">
                    {visibleSuggestions.length} pattern
                    {visibleSuggestions.length !== 1 ? "s" : ""} to review
                  </span>
                </>
              )}
            </div>
          ) : (
            <p className="mt-0.5 text-sm text-gray-500">
              {totalCount} line{totalCount !== 1 ? "s" : ""} awaiting classification
            </p>
          )}
        </div>
        <Link
          href={backUrl}
          className="shrink-0 text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          {backUrl === "/admin/invoices" ? "← All Invoices" : "← Back to Invoice"}
        </Link>
      </div>

      {/* Learning suggestions strip */}
      {visibleSuggestions.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-amber-700">
            Learning Suggestions
          </p>
          <div className="space-y-2">
            {visibleSuggestions.map((s: MappingInsightSuggestion) => (
              <div
                key={s.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-amber-100 bg-white px-3 py-2.5"
              >
                <p className="flex-1 text-sm text-gray-700">💡 {s.message}</p>
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    size="sm"
                    loading={batchConfirmMut.isPending}
                    disabled={batchConfirmMut.isPending}
                    onClick={() =>
                      batchConfirmMut.mutate({
                        line_item_ids: s.line_item_ids,
                        taxonomy_code: s.taxonomy_code,
                        billing_component: s.billing_component,
                      })
                    }
                  >
                    Create Rule
                  </Button>
                  <button
                    className="text-sm text-gray-400 hover:text-gray-600"
                    title="Dismiss"
                    onClick={() => dismissSuggestion(s.id)}
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Grouped queue */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      ) : !groups || groups.length === 0 ? (
        <div className="rounded-xl border bg-white py-16 text-center text-sm text-gray-400 shadow-sm">
          No lines requiring mapping review. The classifier is doing well!
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((g: ReviewQueueGroup) => {
            const groupKey = `${g.supplier_id}:${g.suggested_taxonomy_code ?? "__none__"}`;
            return (
              <GroupCard
                key={groupKey}
                group={g}
                isExpanded={expandedGroups.has(groupKey)}
                onToggleExpand={() => toggleGroup(groupKey)}
                isOverridingGroup={overrideGroupKey === groupKey}
                onToggleGroupOverride={() => toggleGroupOverride(groupKey)}
                overrideItemId={overrideItemId}
                onToggleItemOverride={toggleItemOverride}
                onConfirmAll={() => {
                  setPendingGroupKey(groupKey);
                  batchConfirmMut.mutate({
                    line_item_ids: g.line_item_ids,
                    taxonomy_code: g.suggested_taxonomy_code!,
                    billing_component: g.suggested_billing_component!,
                  });
                }}
                confirmPending={batchConfirmMut.isPending && pendingGroupKey === groupKey}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
