import * as React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative grid w-full items-start gap-y-0.5 rounded border px-4 py-3 text-sm [&>svg]:size-4 [&>svg]:translate-y-0.5 [&>svg]:text-current",
  {
    variants: {
      variant: {
        default: "border-border bg-card text-card-foreground",
        destructive: "border-0 bg-error-100 text-error-500",
        error: "border-0 bg-error-100 text-error-500",
        warning: "border-0 bg-warning-100 text-warning-500",
        info: "border-0 bg-info-100 text-info-500",
        success: "border-0 bg-success-100 text-success-500",
        danger: "border-0 bg-error-100 text-error-500",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

function Alert({ className, variant, ...props }) {
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  );
}

function AlertTitle({ className, ...props }) {
  return (
    <div
      data-slot="alert-title"
      className={cn("min-h-4 font-medium tracking-tight", className)}
      {...props}
    />
  );
}

function AlertDescription({ className, ...props }) {
  return (
    <div
      data-slot="alert-description"
      className={cn("text-sm [&_p]:leading-relaxed", className)}
      {...props}
    />
  );
}

const ALERT_TYPE_CONFIG = {
  Error: {
    bg: "bg-error-100",
    text: "text-error-500",
    closeBg: "bg-error-500",
    btnBorder: "border-error-500",
    icon: "/assets/icons/Alert/ErrorFilled.svg",
  },
  Warning: {
    bg: "bg-warning-100",
    text: "text-warning-500",
    closeBg: "bg-warning-500",
    btnBorder: "border-warning-500",
    icon: "/assets/icons/Alert/WarningFilled.svg",
  },
  Info: {
    bg: "bg-info-100",
    text: "text-info-500",
    closeBg: "bg-info-500",
    btnBorder: "border-info-500",
    icon: "/assets/icons/Alert/InfoFilled.svg",
  },
  Success: {
    bg: "bg-success-100",
    text: "text-success-500",
    closeBg: "bg-success-500",
    btnBorder: "border-success-500",
    icon: "/assets/icons/Alert/SuccessFilled.svg",
  },
};

function AlertBanner({
  type = "Info",
  title,
  description,
  showButton = false,
  buttonLabel = "Button text",
  showClose = true,
  onClose,
  onButtonClick,
  className,
}) {
  const tone = ALERT_TYPE_CONFIG[type] ?? ALERT_TYPE_CONFIG.Info;

  return (
    <div
      role="alert"
      className={cn(
        "relative flex items-start gap-3 rounded border-0 px-4 py-3 text-sm",
        tone.bg,
        tone.text,
        showClose && "pr-10",
        className
      )}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={tone.icon} alt={type} width={24} height={24} className="mt-0 shrink-0" />
      <div className="flex flex-1 flex-col gap-1">
        {title && <span className="font-semibold leading-snug">{title}</span>}
        {description && <span className="leading-relaxed">{description}</span>}
        {showButton && (
          <button
            type="button"
            onClick={onButtonClick}
            className={cn(
              "mt-1 self-start rounded border px-3 py-1 text-xs font-medium transition-colors hover:bg-black/5",
              tone.btnBorder
            )}
          >
            {buttonLabel}
          </button>
        )}
      </div>
      {showClose && (
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 rounded p-1 hover:bg-black/10"
          aria-label="Close"
        >
          <span
            className={cn(
              "block h-6 w-6",
              tone.closeBg,
              "[mask-image:url('/assets/icons/Close/Close_20px.svg')] [mask-size:contain] [mask-repeat:no-repeat]"
            )}
          />
        </button>
      )}
    </div>
  );
}

export { Alert, AlertTitle, AlertDescription, AlertBanner };
