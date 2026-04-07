const STATUS_STYLES: Record<string, string> = {
  // Invoice statuses
  DRAFT: "bg-gray-100 text-gray-600",
  SUBMITTED: "bg-blue-100 text-blue-700",
  PROCESSING: "bg-yellow-100 text-yellow-700",
  REVIEW_REQUIRED: "bg-orange-100 text-orange-700",
  PENDING_CARRIER_REVIEW: "bg-purple-100 text-purple-700",
  CARRIER_REVIEWING: "bg-violet-100 text-violet-700",
  APPROVED: "bg-green-100 text-green-700",
  DISPUTED: "bg-red-100 text-red-700",
  EXPORTED: "bg-teal-100 text-teal-700",
  WITHDRAWN: "bg-gray-200 text-gray-500",
  // Line item statuses
  PENDING: "bg-gray-100 text-gray-600",
  CLASSIFIED: "bg-blue-100 text-blue-700",
  VALIDATED: "bg-green-100 text-green-700",
  EXCEPTION: "bg-red-100 text-red-700",
  DENIED: "bg-red-200 text-red-900",
  OVERRIDE: "bg-yellow-100 text-yellow-700",
  RESOLVED: "bg-teal-100 text-teal-700",
  // Exception / shared statuses
  OPEN: "bg-red-100 text-red-700",
  SUPPLIER_RESPONDED: "bg-indigo-100 text-indigo-700",
  WAIVED: "bg-gray-100 text-gray-500",
};

// Human-readable labels — used as defaults so every screen shows friendly text
const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  PROCESSING: "Processing",
  REVIEW_REQUIRED: "Needs Response",
  PENDING_CARRIER_REVIEW: "Pending Review",
  CARRIER_REVIEWING: "Under Review",
  APPROVED: "Approved",
  DISPUTED: "Disputed",
  EXPORTED: "Exported",
  WITHDRAWN: "Withdrawn",
  PENDING: "Pending",
  CLASSIFIED: "Classified",
  VALIDATED: "Validated",
  EXCEPTION: "Exception",
  DENIED: "Denied",
  OVERRIDE: "Overridden",
  RESOLVED: "Resolved",
  OPEN: "Open",
  SUPPLIER_RESPONDED: "Supplier Responded",
  WAIVED: "Waived",
};

interface StatusBadgeProps {
  status: string;
  label?: string; // optional human-readable override
  className?: string;
}

export function StatusBadge({ status, label, className = "" }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600";
  const displayLabel = label ?? STATUS_LABELS[status] ?? status.replace(/_/g, " ");
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${style} ${className}`}
    >
      {displayLabel}
    </span>
  );
}
