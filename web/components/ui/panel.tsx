import type { ReactNode } from "react";
import type { Hue } from "@/lib/labels";

const STRIPE: Record<Hue, string> = {
  rel: "border-l-[5px] border-l-t-rel",
  req: "border-l-[5px] border-l-t-req",
  match: "border-l-[5px] border-l-t-match",
  share: "border-l-[5px] border-l-t-share",
};

const STRIP: Record<Hue | "candidate", string> = {
  rel: "from-t-rel to-human",
  req: "from-t-req to-human",
  match: "from-t-match to-t-req",
  share: "from-t-share to-t-rel",
  candidate: "from-t-match to-t-req",
};

export const HUE_TEXT: Record<Hue, string> = {
  rel: "text-t-rel-ink",
  req: "text-t-req-ink",
  match: "text-t-match-ink",
  share: "text-t-share-ink",
};

export function Panel({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return <Tag className={`rounded border border-rule bg-panel ${className}`}>{children}</Tag>;
}

export function PanelRow({ children, hue, className = "" }: { children: ReactNode; hue?: Hue; className?: string }) {
  return (
    <div className={`border-t border-rule px-3.5 py-3 first:border-t-0 ${hue ? STRIPE[hue] : ""} ${className}`}>
      {children}
    </div>
  );
}

export function SectionLabel({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="mb-2 text-xs font-bold uppercase tracking-[0.07em] text-human-ink">
      {children}
    </h2>
  );
}

export function PageHeader({
  title,
  sub,
  hue = "req",
  actions,
}: {
  title: string;
  sub?: ReactNode;
  hue?: Hue | "candidate";
  actions?: ReactNode;
}) {
  return (
    <header className="mb-5">
      <div aria-hidden="true" className={`mb-3 h-1 rounded-full bg-gradient-to-r ${STRIP[hue]}`} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="break-words text-[26px] font-bold leading-tight tracking-tight">{title}</h1>
          {sub ? <p className="mt-1 max-w-2xl text-mut">{sub}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
