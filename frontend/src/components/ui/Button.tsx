import { clsx } from "clsx";

type ButtonVariant = "primary" | "secondary" | "ghost" | "outline";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  children: React.ReactNode;
  className?: string;
  type?: "button" | "submit";
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-b from-emerald-400 to-emerald-500 text-emerald-950 shadow-sm " +
    "hover:from-emerald-300 hover:to-emerald-400 hover:shadow-glow-emerald " +
    "dark:from-emerald-400 dark:to-emerald-500 dark:text-emerald-950",
  secondary:
    "bg-zinc-100 text-zinc-900 border border-zinc-300/80 shadow-sm hover:bg-zinc-200 hover:border-zinc-400/60 " +
    "dark:bg-zinc-800/80 dark:text-zinc-100 dark:border-zinc-700/80 dark:hover:bg-zinc-700/80 dark:hover:border-zinc-600",
  ghost:
    "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/70 dark:hover:text-zinc-100",
  outline:
    "border border-zinc-300 bg-transparent hover:bg-zinc-100 hover:border-zinc-400 " +
    "dark:border-zinc-600 dark:hover:bg-zinc-800/70 dark:hover:border-zinc-500",
};

const sizeClasses = { sm: "h-7 px-2.5 text-xs gap-1.5", md: "h-9 px-3.5 text-sm gap-2" };

export function Button({
  variant = "primary",
  size = "md",
  children,
  className,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        "inline-flex select-none items-center justify-center rounded-lg font-medium",
        "transition-all duration-150 ease-out active:scale-[0.97]",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-950",
        "disabled:pointer-events-none disabled:opacity-50",
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
      disabled={disabled}
      {...rest}
    >
      {children}
    </button>
  );
}
