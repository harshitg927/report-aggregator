import * as React from "react";
import { cn } from "@/lib/utils";

const Select = React.forwardRef(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "w-full rounded border border-neutral-800 bg-white px-3 py-2 text-sm text-neutral-800 transition-colors",
      "focus:border-primary focus:shadow-[0px_0px_3px_2px_#00449440] focus:outline-none",
      "disabled:cursor-not-allowed disabled:border-border disabled:text-neutral-600",
      className
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";

export { Select };
