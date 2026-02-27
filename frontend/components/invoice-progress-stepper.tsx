"use client";

interface StepState {
  completedUpTo: number; // steps with index < this are filled/checked
  activeStep: number;    // -1 if not yet started
  warningStep: number;   // -1 or step index shown in warning style
  isDone: boolean;
  isWithdrawn: boolean;
  responseLabel: string; // dynamic label for step index 2
}

function getStepState(status: string): StepState {
  switch (status) {
    case "DRAFT":
      return { completedUpTo: 0, activeStep: -1, warningStep: -1, isDone: false, isWithdrawn: false, responseLabel: "Response" };
    case "SUBMITTED":
      return { completedUpTo: 0, activeStep: 0, warningStep: -1, isDone: false, isWithdrawn: false, responseLabel: "Response" };
    case "PROCESSING":
      return { completedUpTo: 1, activeStep: 1, warningStep: -1, isDone: false, isWithdrawn: false, responseLabel: "Response" };
    case "REVIEW_REQUIRED":
      return { completedUpTo: 2, activeStep: 2, warningStep: 2, isDone: false, isWithdrawn: false, responseLabel: "Response Needed" };
    case "SUPPLIER_RESPONDED":
      return { completedUpTo: 3, activeStep: 3, warningStep: -1, isDone: false, isWithdrawn: false, responseLabel: "Responded" };
    case "PENDING_CARRIER_REVIEW":
      return { completedUpTo: 3, activeStep: 3, warningStep: -1, isDone: false, isWithdrawn: false, responseLabel: "Responded" };
    case "CARRIER_REVIEWING":
      return { completedUpTo: 3, activeStep: 3, warningStep: -1, isDone: false, isWithdrawn: false, responseLabel: "Responded" };
    case "APPROVED":
    case "EXPORTED":
      return { completedUpTo: 5, activeStep: 4, warningStep: -1, isDone: true, isWithdrawn: false, responseLabel: "Responded" };
    case "DISPUTED":
      return { completedUpTo: 4, activeStep: 4, warningStep: 4, isDone: true, isWithdrawn: false, responseLabel: "Responded" };
    case "WITHDRAWN":
      return { completedUpTo: 0, activeStep: -1, warningStep: -1, isDone: false, isWithdrawn: true, responseLabel: "Response" };
    default:
      return { completedUpTo: 0, activeStep: -1, warningStep: -1, isDone: false, isWithdrawn: false, responseLabel: "Response" };
  }
}

const STEP_BASE_LABELS = ["Submitted", "Validation", "Response", "Carrier Review", "Complete"];

interface InvoiceProgressStepperProps {
  status: string;
}

export function InvoiceProgressStepper({ status }: InvoiceProgressStepperProps) {
  const { completedUpTo, activeStep, warningStep, isDone, isWithdrawn, responseLabel } =
    getStepState(status);

  if (isWithdrawn) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
        <span className="text-sm text-gray-400">
          Invoice withdrawn — no further processing
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center" role="list" aria-label="Invoice progress">
      {STEP_BASE_LABELS.map((baseLabel, i) => {
        const label = i === 2 ? responseLabel : baseLabel;
        const isCompleted = i < completedUpTo;
        const isActive = i === activeStep;
        const isWarning = i === warningStep;

        // Determine circle appearance
        let circleClass = "";
        let labelClass = "";
        let circleContent: React.ReactNode;

        if (isCompleted && warningStep !== i) {
          // Fully completed step
          circleClass = "bg-green-500 text-white";
          circleContent = (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          );
          labelClass = "text-green-700 font-medium";
        } else if (isActive && isWarning) {
          // Active + warning (REVIEW_REQUIRED → orange; DISPUTED final step → red)
          const isDisputed = warningStep === 4 && isDone;
          circleClass = isDisputed
            ? "bg-red-500 text-white ring-2 ring-red-300 ring-offset-1"
            : "bg-orange-500 text-white ring-2 ring-orange-300 ring-offset-1";
          circleContent = <span className="text-xs font-bold">!</span>;
          labelClass = isDisputed ? "text-red-700 font-semibold" : "text-orange-700 font-semibold";
        } else if (isActive && isDone) {
          // Done + no warning (APPROVED/EXPORTED final step)
          circleClass = "bg-green-500 text-white ring-2 ring-green-300 ring-offset-1";
          circleContent = (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          );
          labelClass = "text-green-700 font-semibold";
        } else if (isActive) {
          // Normal active step
          circleClass = "bg-blue-600 text-white ring-2 ring-blue-300 ring-offset-1";
          circleContent = <span className="text-xs font-bold">{i + 1}</span>;
          labelClass = "text-blue-700 font-semibold";
        } else {
          // Future step
          circleClass = "bg-gray-200 text-gray-400";
          circleContent = <span className="text-xs">{i + 1}</span>;
          labelClass = "text-gray-400";
        }

        return (
          <div key={baseLabel} className="flex flex-1 items-center" role="listitem">
            {/* Step node */}
            <div className="flex flex-col items-center gap-1.5 min-w-0">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full transition-all flex-shrink-0 ${circleClass}`}
              >
                {circleContent}
              </div>
              <span className={`whitespace-nowrap text-xs ${labelClass}`}>
                {label}
              </span>
            </div>

            {/* Connector line (not after last step) */}
            {i < STEP_BASE_LABELS.length - 1 && (
              <div
                className={`mx-2 mb-4 h-px flex-1 transition-colors ${
                  i < completedUpTo ? "bg-green-400" : "bg-gray-200"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
