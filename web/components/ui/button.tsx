import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from "react";
import Link from "next/link";

type Variant = "primary" | "secondary" | "quiet" | "danger";

const BASE =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded px-3.5 text-[13px] font-semibold leading-none whitespace-nowrap transition-colors sm:min-h-8 sm:px-3 disabled:cursor-not-allowed disabled:opacity-50";

const VARIANT: Record<Variant, string> = {
  primary: "bg-human text-white hover:bg-human-ink",
  secondary: "border border-rule-strong bg-panel text-ink hover:bg-inset",
  quiet: "text-human-ink hover:bg-human-bg",
  danger: "border border-bad-ink bg-panel text-bad-ink hover:bg-bad-bg",
};

export function Button({
  variant = "secondary",
  busy = false,
  className = "",
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button
      type={type}
      className={`${BASE} ${VARIANT[variant]} ${className}`}
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
  className = "",
  href,
  children,
  prefetch = false,
  ...rest
}: Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  variant?: Exclude<Variant, "danger">;
  href: string;
  prefetch?: boolean;
}) {
  return (
    <Link href={href} prefetch={prefetch} className={`${BASE} ${VARIANT[variant]} no-underline ${className}`} {...rest}>
      {children}
    </Link>
  );
}
