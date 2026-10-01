import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";
import Link from "next/link";

type Variant = "primary" | "secondary" | "quiet" | "danger";
type Size = "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-[2px] font-semibold leading-none whitespace-nowrap no-underline transition-colors disabled:cursor-not-allowed disabled:opacity-50";

const SIZE: Record<Size, string> = {
  md: "min-h-11 px-3.5 text-[13px] sm:min-h-9",
  lg: "min-h-12 px-5 text-[14px]",
};

const VARIANT: Record<Variant, string> = {
  primary: "bg-human text-white shadow-[inset_0_-2px_0_rgba(0,0,0,0.18)] hover:bg-human-ink",
  secondary: "border border-rule-strong/60 bg-panel text-ink hover:border-rule-strong hover:bg-inset",
  quiet: "text-human-ink hover:bg-human-bg",
  danger: "border border-bad-ink bg-panel text-bad-ink hover:bg-bad-bg",
};

export function Button({
  variant = "secondary",
  size = "md",
  busy = false,
  className = "",
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; busy?: boolean }) {
  return (
    <button
      type={type}
      className={`${BASE} ${SIZE[size]} ${VARIANT[variant]} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {children}
    </button>
  );
}

export function LinkButton({
  variant = "secondary",
  size = "md",
  className = "",
  href,
  children,
  prefetch = false,
  ...rest
}: Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  variant?: Exclude<Variant, "danger">;
  size?: Size;
  href: string;
  prefetch?: boolean;
}) {
  return (
    <Link href={href} prefetch={prefetch} className={`${BASE} ${SIZE[size]} ${VARIANT[variant]} ${className}`} {...rest}>
      {children}
    </Link>
  );
}
