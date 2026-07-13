"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/", label: "Dashboard", exact: true },
  { href: "/merge", label: "New Merge", icon: "/assets/icons/Plus/Plus_20px.svg" },
];

export function Header() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 flex h-13 items-center justify-between border-b border-neutral-300 bg-neutral-300 px-6 text-sm">
      <Link href="/" className="flex items-center gap-3 no-underline">
        <img
          src="/assets/images/logo.svg"
          alt="FOSSology"
          width={120}
          height={32}
          className="h-8 w-auto"
        />
        <span className="font-semibold text-foreground">Report Aggregator</span>
      </Link>

      <nav className="flex items-center gap-1">
        {NAV_LINKS.map((link) => {
          const active = link.exact
            ? pathname === link.href
            : pathname === link.href || pathname.startsWith(`${link.href}/`);

          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "inline-flex items-center gap-1.5 px-4 py-3 text-sm font-medium text-foreground no-underline transition-colors hover:text-tertiary1-800",
                active && "border-b-2 border-brand-900 text-tertiary1-900"
              )}
            >
              {link.icon && (
                <img
                  src={link.icon}
                  alt=""
                  width={16}
                  height={16}
                  aria-hidden
                  className="h-4 w-4"
                />
              )}
              {link.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
