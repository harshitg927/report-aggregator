/*
 SPDX-FileCopyrightText: © 2026 Harshit Gandhi <gandhiharshit716@gmail.com>

 SPDX-License-Identifier: MIT
*/

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-[10px] whitespace-nowrap rounded text-sm font-medium transition-colors disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none",
  {
    variants: {
      variant: {
        default:
          "bg-tertiary1-800 text-white hover:bg-tertiary1-900 disabled:bg-tertiary1-400 disabled:text-white",
        outline:
          "border border-tertiary1-800 text-tertiary1-800 bg-white hover:bg-tertiary1-200 hover:border-tertiary1-800 disabled:border-tertiary1-400 disabled:text-tertiary1-400 disabled:bg-white disabled:opacity-100",
        link:
          "text-tertiary1-800 bg-transparent border-none underline-offset-4 hover:underline hover:text-tertiary1-900 hover:decoration-tertiary1-900 disabled:text-tertiary1-400 disabled:underline disabled:decoration-tertiary1-400 disabled:opacity-100",
        alert:
          "bg-alert text-white hover:bg-alert-hover disabled:bg-alert disabled:opacity-40",
        "alert-outline":
          "border border-alert text-alert bg-white hover:bg-alert-bg hover:border-alert disabled:border-alert disabled:text-alert disabled:bg-white disabled:opacity-40",
        "alert-link":
          "text-alert bg-transparent border-none underline-offset-4 hover:bg-alert-bg hover:underline hover:text-alert hover:decoration-alert disabled:text-alert disabled:opacity-40",
        destructive:
          "bg-alert text-white hover:bg-alert-hover disabled:bg-alert disabled:opacity-40",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
      },
      size: {
        default: "h-10 px-8 py-2",
        md: "h-8 px-4 py-1",
        sm: "h-6 px-3 py-1 text-xs gap-1",
        icon: "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

const Button = React.forwardRef(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        data-slot="button"
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
