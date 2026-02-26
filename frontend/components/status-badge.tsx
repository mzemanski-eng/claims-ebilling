const STATUS_STYLES: Record<string, string> = {
  DRAFT: "bg-gray-100 text-gray-600",
  SUBMITTED: "bg-blue-100 text-blue-700",
  PROCESSING: "bg-yellow-100 text-yellow-700",
  REVIEW_REQUIRED: "bg-orange-100 text-orange-700",
  SUPPLIER_RESPONDED: "bg-indigo-100 text-indigo-700",
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
  OVERRIDE: "bg-yellow-100 text-yellow-700",
  RESOLVED: "bg-teal-100 text-teal-700",
  // Exception statuses
  OPEN: "bg-red-100 text-red-700",
  SUPPLIER_RESPONDED: "bg-indigo-100 text-indigo-700",
  WAIVED: "bg-gray-100 text-gray-500",
};

interface StatusBadgeProps {
  status: string;
  className?: string;
}

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600";
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${style} ${className}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
