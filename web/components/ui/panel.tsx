import type { ReactNode } from "react";
import type { Hue } from "@/lib/labels";
import { Icon, type IconName } from "./icons";

const STRIPE: Record<Hue, string> = {
  rel: "border-l-[3px] border-l-t-rel",
  req: "border-l-[3px] border-l-t-req",
  match: "border-l-[3px] border-l-t-match",
  share: "border-l-[3px] border-l-t-share",
};

export const HUE_TEXT: Record<Hue, string> = {
  rel: "text-t-rel-ink",
  req: "text-t-req-ink",
  match: "text-t-match-ink",
  share: "text-t-share-ink",
};

const TILE: Record<Hue | "human" | "prop" | "bad" | "ok", string> = {
  rel: "bg-t-rel-bg text-t-rel-ink",
  req: "bg-t-req-bg text-t-req-ink",
  match: "bg-t-match-bg text-t-match-ink",
  share: "bg-t-share-bg text-t-share-ink",
  human: "bg-human-bg text-human-ink",
  prop: "bg-prop-bg text-prop-ink",
  bad: "bg-bad-bg text-bad-ink",
  ok: "bg-ok-bg text-ok-ink",
};

/** The small tinted square that carries an icon in KPI tiles and queue rows. */
export function IconTile({ name, tone }: { name: IconName; tone: keyof typeof TILE }) {
  return (
    <span className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[2px] ${TILE[tone]}`}>
      <Icon name={name} size={17} />
    </span>
  );
}

export function Panel({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return <Tag className={`border border-rule bg-panel ${className}`}>{children}</Tag>;
}

export function PanelRow({ children, hue, className = "" }: { children: ReactNode; hue?: Hue; className?: string }) {
  return (
    <div className={`border-t border-rule px-5 py-3.5 first:border-t-0 ${hue ? STRIPE[hue] : ""} ${className}`}>
      {children}
    </div>
  );
}

/** Mono, uppercase, tracked. Used for the small labels above panel titles ("WORK QUEUES"). */
export function Eyebrow({ children, dot = false, className = "" }: { children: ReactNode; dot?: boolean; className?: string }) {
  return (
    <p className={`flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-mut ${className}`}>
      {dot ? <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-ok" /> : null}
      {children}
    </p>
  );
}

export function SectionLabel({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="mb-2.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-mut">
      {children}
    </h2>
  );
}

/** A panel's header: small mono eyebrow, a title, and an optional action on the right. */
export function PanelHeader({
  eyebrow,
  title,
  action,
  id,
}: {
  eyebrow?: string;
  title: ReactNode;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-rule px-5 py-4">
      <div className="min-w-0">
        {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
        <h2 id={id} className="mt-1 text-[17px] font-semibold tracking-tight text-ink">
          {title}
        </h2>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

/** Section title with the short rule to its right, as in the approved candidate record. */
export function RuleHeading({ children, id, as: Tag = "h2" }: { children: ReactNode; id?: string; as?: "h2" | "h3" }) {
  return (
    <Tag id={id} className="rule-heading mb-4 text-[19px] font-semibold tracking-tight text-ink">
      {children}
    </Tag>
  );
}

export function PageHeader({
  title,
  sub,
  eyebrow,
  actions,
}: {
  title: string;
  sub?: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-7">
      {eyebrow ? <Eyebrow dot className="mb-3">{eyebrow}</Eyebrow> : null}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="break-words text-[32px] font-semibold leading-[1.08] tracking-[-0.025em] text-ink sm:text-[44px]">
            {title}
          </h1>
          {sub ? <p className="mt-2.5 max-w-2xl text-[15px] text-mut">{sub}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
