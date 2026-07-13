import { cn } from "@/lib/utils";

export function DataTable({ columns, children, className }) {
  return (
    <div className={cn("overflow-x-auto border border-border", className)}>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-neutral-200">
            {columns.map((col) => (
              <th
                key={col}
                className="border-b border-border px-3 py-2 text-left font-medium"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function DataTableRow({ children, className, ...props }) {
  return (
    <tr
      className={cn(
        "border-b border-border even:bg-neutral-100 hover:bg-accent/30",
        className
      )}
      {...props}
    >
      {children}
    </tr>
  );
}

export function DataTableCell({ children, className, align = "left", ...props }) {
  return (
    <td
      className={cn(
        "px-3 py-2 align-middle",
        align === "center" && "text-center",
        align === "right" && "text-right",
        className
      )}
      {...props}
    >
      {children}
    </td>
  );
}
