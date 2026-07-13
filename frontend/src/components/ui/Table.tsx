import { Children, isValidElement } from "react";
import { clsx } from "clsx";

export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className="overflow-x-auto rounded-lg">
      <table className={clsx("w-full text-sm", className)}>{children}</table>
    </div>
  );
}

export function TableHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  // R34.0 DOM fix: consumers use two patterns — passing <TableHead> cells
  // directly, or wrapping them in a <TableRow>. Wrapping unconditionally caused
  // `<tr> cannot appear as a child of <tr>`. Detect an existing row and only add
  // the header <tr> when the caller did not supply one.
  const alreadyHasRow = Children.toArray(children).some(
    (child) => isValidElement(child) && child.type === TableRow
  );
  return (
    <thead className="glass sticky top-0 z-[1]">
      {alreadyHasRow ? (
        children
      ) : (
        <tr
          className={clsx(
            "border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700/80 dark:text-zinc-500",
            className
          )}
        >
          {children}
        </tr>
      )}
    </thead>
  );
}

export function TableBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <tbody className={className}>{children}</tbody>;
}

export function TableRow({
  children,
  className,
  onClick,
  ...rest
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
} & React.ComponentPropsWithoutRef<"tr">) {
  return (
    <tr
      className={clsx(
        "border-b border-zinc-100 last:border-0 transition-colors duration-150 dark:border-zinc-800/50",
        "hover:bg-emerald-50/40 dark:hover:bg-zinc-800/50",
        onClick &&
          "cursor-pointer hover:shadow-[inset_2px_0_0_0_rgb(16_185_129/0.7)] active:bg-emerald-50/70 dark:active:bg-zinc-800/80",
        className
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      {...rest}
    >
      {children}
    </tr>
  );
}

export function TableHead({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={clsx(
        "py-3 pr-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-500",
        className
      )}
    >
      {children}
    </th>
  );
}

export function TableCell({
  children,
  className,
  numeric,
  title,
}: {
  children: React.ReactNode;
  className?: string;
  numeric?: boolean;
  title?: string;
}) {
  return (
    <td
      className={clsx("py-3 pr-2", numeric && "font-mono text-right tabular-nums", className)}
      title={title}
    >
      {children}
    </td>
  );
}
