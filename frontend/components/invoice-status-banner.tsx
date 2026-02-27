"use client";

interface BannerConfig {
  border: string;
  bg: string;
  iconBg: string;
  iconColor: string;
  headingColor: string;
  bodyColor: string;
  icon: React.ReactNode;
  headline: string;
  body: string;
  cta?: { label: string; scrollTo: string } | { label: string; href: string };
}

const BANNER_CONFIGS: Record<string, BannerConfig> = {
  DRAFT: {
    border: "border-gray-200",
    bg: "bg-gray-50",
    iconBg: "bg-gray-200",
    iconColor: "text-gray-500",
    headingColor: "text-gray-800",
    bodyColor: "text-gray-600",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
    headline: "Invoice saved as draft",
    body: "Your invoice has been saved but not yet submitted. Upload your invoice file to begin processing.",
  },

  SUBMITTED: {
    border: "border-blue-200",
    bg: "bg-blue-50",
    iconBg: "bg-blue-100",
    iconColor: "text-blue-600",
    headingColor: "text-blue-900",
    bodyColor: "text-blue-700",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    headline: "Invoice received — awaiting processing",
    body: "We've received your invoice. The system is queued to validate your line items against your contract. No action needed right now.",
  },

  PROCESSING: {
    border: "border-yellow-200",
    bg: "bg-yellow-50",
    iconBg: "bg-yellow-100",
    iconColor: "text-yellow-600",
    headingColor: "text-yellow-900",
    bodyColor: "text-yellow-700",
    icon: (
      <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
    headline: "Your invoice is being validated",
    body: "Line items are being checked against your contract rates and billing guidelines. This usually takes just a few minutes — check back shortly.",
  },

  REVIEW_REQUIRED: {
    border: "border-orange-200",
    bg: "bg-orange-50",
    iconBg: "bg-orange-100",
    iconColor: "text-orange-600",
    headingColor: "text-orange-900",
    bodyColor: "text-orange-700",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    headline: "Action required — exceptions need your response",
    body: "One or more line items could not be validated automatically. Please review the exceptions below, provide your explanation for each one, then resubmit your invoice.",
    cta: { label: "Jump to exceptions", scrollTo: "exceptions" },
  },

  SUPPLIER_RESPONDED: {
    border: "border-indigo-200",
    bg: "bg-indigo-50",
    iconBg: "bg-indigo-100",
    iconColor: "text-indigo-600",
    headingColor: "text-indigo-900",
    bodyColor: "text-indigo-700",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-3 3-3-3z" />
      </svg>
    ),
    headline: "Your responses have been submitted",
    body: "Thank you — the carrier is reviewing your responses to the exceptions raised. You'll be notified if any further action is needed. No action required right now.",
  },

  PENDING_CARRIER_REVIEW: {
    border: "border-purple-200",
    bg: "bg-purple-50",
    iconBg: "bg-purple-100",
    iconColor: "text-purple-600",
    headingColor: "text-purple-900",
    bodyColor: "text-purple-700",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    headline: "In the carrier's review queue",
    body: "Your invoice has passed initial validation and is waiting for a carrier reviewer. No action needed from you — we'll update this page when a decision is reached.",
  },

  CARRIER_REVIEWING: {
    border: "border-violet-200",
    bg: "bg-violet-50",
    iconBg: "bg-violet-100",
    iconColor: "text-violet-600",
    headingColor: "text-violet-900",
    bodyColor: "text-violet-700",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
      </svg>
    ),
    headline: "A carrier reviewer is actively reviewing your invoice",
    body: "This invoice is under active review by the carrier team. No action needed. You'll be notified when they reach a decision.",
  },

  APPROVED: {
    border: "border-green-200",
    bg: "bg-green-50",
    iconBg: "bg-green-100",
    iconColor: "text-green-600",
    headingColor: "text-green-900",
    bodyColor: "text-green-700",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    headline: "Invoice approved — payment will be issued",
    body: "The carrier has approved your invoice. Payment will be processed according to your contract terms. Your approved payment amount is shown below.",
  },

  DISPUTED: {
    border: "border-red-200",
    bg: "bg-red-50",
    iconBg: "bg-red-100",
    iconColor: "text-red-600",
    headingColor: "text-red-900",
    bodyColor: "text-red-700",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    headline: "Invoice disputed by carrier",
    body: "The carrier has raised a formal dispute on this invoice. Please contact your carrier representative to resolve. Review the line item exceptions below for details.",
    cta: { label: "See disputed lines", scrollTo: "exceptions" },
  },

  EXPORTED: {
    border: "border-teal-200",
    bg: "bg-teal-50",
    iconBg: "bg-teal-100",
    iconColor: "text-teal-600",
    headingColor: "text-teal-900",
    bodyColor: "text-teal-700",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
    ),
    headline: "Invoice exported to payment system",
    body: "This invoice has been approved and exported to the payment processing system. Payment will be issued according to your contract payment terms.",
  },

  WITHDRAWN: {
    border: "border-gray-200",
    bg: "bg-gray-100",
    iconBg: "bg-gray-200",
    iconColor: "text-gray-400",
    headingColor: "text-gray-600",
    bodyColor: "text-gray-500",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
    headline: "Invoice withdrawn",
    body: "This invoice has been withdrawn and will not be processed. If this was in error, please submit a new invoice.",
  },
};

const FALLBACK_CONFIG: BannerConfig = {
  border: "border-gray-200",
  bg: "bg-gray-50",
  iconBg: "bg-gray-100",
  iconColor: "text-gray-500",
  headingColor: "text-gray-800",
  bodyColor: "text-gray-600",
  icon: (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  headline: "Invoice status updated",
  body: "Your invoice status has changed. Check back for further updates.",
};

interface InvoiceStatusBannerProps {
  status: string;
  invoiceId?: string;
}

export function InvoiceStatusBanner({ status }: InvoiceStatusBannerProps) {
  const config = BANNER_CONFIGS[status] ?? FALLBACK_CONFIG;

  let ctaElement: React.ReactNode = null;
  if (config.cta) {
    if ("scrollTo" in config.cta) {
      ctaElement = (
        <a
          href={`#${config.cta.scrollTo}`}
          className={`mt-2 inline-flex items-center gap-1 text-sm font-medium underline underline-offset-2 ${config.headingColor}`}
        >
          {config.cta.label} ↓
        </a>
      );
    } else {
      ctaElement = (
        <a
          href={config.cta.href}
          className={`mt-2 inline-flex items-center gap-1 text-sm font-medium underline underline-offset-2 ${config.headingColor}`}
        >
          {config.cta.label} →
        </a>
      );
    }
  }

  return (
    <div className={`rounded-lg border ${config.border} ${config.bg} px-4 py-4 flex gap-3`}>
      {/* Icon circle */}
      <div
        className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${config.iconBg} ${config.iconColor}`}
      >
        {config.icon}
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-semibold ${config.headingColor}`}>
          {config.headline}
        </p>
        <p className={`mt-0.5 text-sm ${config.bodyColor}`}>
          {config.body}
        </p>
        {ctaElement}
      </div>
    </div>
  );
}
