"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Settings, Zap, Shield, Brain, DollarSign, AlertTriangle } from "lucide-react";
import { getCarrierSettings, updateCarrierSettings } from "@/lib/api";
import type { CarrierSettings } from "@/lib/types";

// ── Helpers ────────────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-blue-600" : "bg-gray-200"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

function AmountInput({
  value,
  onChange,
  placeholder,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative max-w-xs">
      <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-400 text-sm">
        $
      </span>
      <input
        type="number"
        min={0}
        step={500}
        value={value ?? ""}
        placeholder={placeholder ?? "No limit"}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === "" ? null : Number(v));
        }}
        className="w-full rounded-lg border border-gray-300 py-2 pl-7 pr-3 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50"
      />
    </div>
  );
}

function RadioGroup<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; description: string }[];
}) {
  return (
    <div className="space-y-2">
      {options.map((opt) => (
        <label
          key={opt.value}
          className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
            value === opt.value
              ? "border-blue-300 bg-blue-50"
              : "border-gray-200 bg-white hover:border-gray-300"
          }`}
        >
          <input
            type="radio"
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
            className="mt-0.5 h-4 w-4 cursor-pointer text-blue-600 focus:ring-blue-500"
          />
          <div>
            <p className="text-sm font-medium text-gray-800">{opt.label}</p>
            <p className="text-xs text-gray-500">{opt.description}</p>
          </div>
        </label>
      ))}
    </div>
  );
}

// ── Settings Card ─────────────────────────────────────────────────────────────

function SettingsSection({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border bg-white p-6 shadow-sm">
      <div className="mb-5 flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          {icon}
        </div>
        <div>
          <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
          <p className="mt-0.5 text-xs text-gray-500">{description}</p>
        </div>
      </div>
      <div className="space-y-5">{children}</div>
    </div>
  );
}

function SettingsRow({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-6">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-800">{label}</p>
        {description && <p className="mt-0.5 text-xs text-gray-500">{description}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

// ── Default settings ──────────────────────────────────────────────────────────

const DEFAULT_SETTINGS: CarrierSettings = {
  auto_approve_clean_invoices: null,
  auto_approve_max_amount: null,
  require_review_above_amount: null,
  risk_tolerance: "standard",
  ai_classification_mode: "auto",
};

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const qc = useQueryClient();
  const [saved, setSaved] = useState(false);
  const [draft, setDraft] = useState<CarrierSettings | null>(null);

  const { data: remote, isLoading } = useQuery({
    queryKey: ["carrier-settings"],
    queryFn: getCarrierSettings,
  });

  // Populate draft once on initial load
  useEffect(() => {
    if (remote && draft === null) setDraft(remote);
  }, [remote]); // eslint-disable-line react-hooks/exhaustive-deps

  const mutation = useMutation({
    mutationFn: updateCarrierSettings,
    onSuccess: (data) => {
      qc.setQueryData(["carrier-settings"], data);
      setDraft(data);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
  });

  const settings: CarrierSettings = draft ?? remote ?? DEFAULT_SETTINGS;

  function update<K extends keyof CarrierSettings>(key: K, value: CarrierSettings[K]) {
    setDraft((prev): CarrierSettings => ({ ...(prev ?? remote ?? DEFAULT_SETTINGS), [key]: value }));
  }

  const isDirty = JSON.stringify(draft) !== JSON.stringify(remote);

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-gray-400">
        Loading settings…
      </div>
    );
  }

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Settings className="h-5 w-5 text-gray-500" />
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Platform Settings</h1>
            <p className="text-sm text-gray-500">
              Configure how invoices are processed and reviewed for your organisation.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {saved && (
            <span className="text-sm font-medium text-green-600">
              ✓ Settings saved
            </span>
          )}
          <button
            onClick={() => setDraft(remote ?? DEFAULT_SETTINGS as CarrierSettings)}
            disabled={!isDirty || mutation.isPending}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
          >
            Reset
          </button>
          <button
            onClick={() => mutation.mutate(settings)}
            disabled={!isDirty || mutation.isPending}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {mutation.isPending ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>

      {mutation.isError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Failed to save settings. Please try again.
        </div>
      )}

      {/* Invoice Processing */}
      <SettingsSection
        icon={<Zap className="h-4 w-4" />}
        title="Invoice Processing"
        description="Control when invoices are automatically approved vs. queued for human review."
      >
        <SettingsRow
          label="Auto-approve clean invoices"
          description={
            settings.auto_approve_clean_invoices === null
              ? "Using platform default (enabled). Invoices with zero billing errors are approved automatically."
              : settings.auto_approve_clean_invoices
              ? "Enabled — clean invoices are approved without carrier review."
              : "Disabled — all invoices are queued for carrier review."
          }
        >
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">
              {settings.auto_approve_clean_invoices === null ? "Platform default" : "Custom"}
            </span>
            <Toggle
              checked={settings.auto_approve_clean_invoices ?? true}
              onChange={(v) => update("auto_approve_clean_invoices", v)}
            />
          </div>
        </SettingsRow>

        <div className="border-t border-gray-100" />

        <SettingsRow
          label="Auto-approve limit"
          description="Only auto-approve invoices at or below this amount. Leave blank for no limit."
        >
          <AmountInput
            value={settings.auto_approve_max_amount}
            onChange={(v) => update("auto_approve_max_amount", v)}
            placeholder="No limit"
          />
        </SettingsRow>

        <div className="border-t border-gray-100" />

        <SettingsRow
          label="Always review above"
          description="Force carrier review for any invoice exceeding this amount, even if it is clean. Leave blank to disable."
        >
          <AmountInput
            value={settings.require_review_above_amount}
            onChange={(v) => update("require_review_above_amount", v)}
            placeholder="Disabled"
          />
        </SettingsRow>

        {/* Amount guard summary */}
        {(settings.auto_approve_max_amount || settings.require_review_above_amount) && (
          <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-700">
            <span className="font-semibold">Amount rules active:</span>{" "}
            {settings.auto_approve_max_amount && (
              <>
                auto-approve only when total ≤ ${settings.auto_approve_max_amount.toLocaleString()}
                {settings.require_review_above_amount ? "; " : "."}
              </>
            )}
            {settings.require_review_above_amount && (
              <>
                always review when total &gt; ${settings.require_review_above_amount.toLocaleString()}.
              </>
            )}
          </div>
        )}
      </SettingsSection>

      {/* AI Classification */}
      <SettingsSection
        icon={<Brain className="h-4 w-4" />}
        title="AI Classification Behaviour"
        description="Control how the AI handles unrecognised billing codes."
      >
        <RadioGroup
          value={settings.ai_classification_mode}
          onChange={(v) => update("ai_classification_mode", v)}
          options={[
            {
              value: "auto",
              label: "Auto-resolve (recommended)",
              description:
                "AI automatically reclassifies line items with HIGH or MEDIUM confidence suggestions. No human review needed for classification-only exceptions.",
            },
            {
              value: "supervised",
              label: "Supervised",
              description:
                "All classification exceptions are queued for carrier review, even when AI confidence is high. Choose this if your team wants to confirm every reclassification.",
            },
          ]}
        />
      </SettingsSection>

      {/* Risk Tolerance */}
      <SettingsSection
        icon={<Shield className="h-4 w-4" />}
        title="Risk Tolerance"
        description="Adjust how aggressively the pipeline flags invoices for review."
      >
        <RadioGroup
          value={settings.risk_tolerance}
          onChange={(v) => update("risk_tolerance", v)}
          options={[
            {
              value: "strict",
              label: "Strict",
              description:
                "WARNING-severity exceptions are treated as errors and trigger carrier review. Most conservative — maximises oversight.",
            },
            {
              value: "standard",
              label: "Standard (recommended)",
              description:
                "Only ERROR-severity exceptions trigger review. WARNING exceptions are noted but do not block approval. Platform default.",
            },
            {
              value: "relaxed",
              label: "Relaxed",
              description:
                "Only confirmed rate or spend billing errors require review. Classification warnings pass automatically.",
            },
          ]}
        />
      </SettingsSection>

      {/* Platform defaults reminder */}
      <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-xs text-gray-500">
        <span className="font-medium text-gray-700">Platform defaults: </span>
        auto-approve clean invoices on · no amount limits · standard risk tolerance · AI auto-resolution on.
        Fields set to their null/default value inherit the platform setting and will adapt automatically
        when the platform default changes.
      </div>

    </div>
  );
}
