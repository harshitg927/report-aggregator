import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef(({ className, type, ...props }, ref) => (
  <input
    type={type}
    ref={ref}
    data-slot="input"
    className={cn(
      "w-full rounded border border-neutral-800 bg-white px-3 py-2 text-sm transition-colors caret-primary placeholder:text-neutral-600",
      "focus:border-primary focus:shadow-[0px_0px_3px_2px_#00449440] focus:outline-none",
      "disabled:pointer-events-none disabled:cursor-not-allowed disabled:border-border disabled:text-neutral-600 disabled:placeholder:text-neutral-600",
      className
    )}
    {...props}
  />
));
Input.displayName = "Input";

export { Input };
