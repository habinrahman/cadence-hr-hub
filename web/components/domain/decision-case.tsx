import type { ReactNode } from "react";
import type { Hue } from "@/lib/labels";
import { PanelRow, SectionLabel } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";

/**
 * Every consequential decision has the same anatomy:
 * Found, Evidence, Proposed, Decision, Record.
 * The Proposed block is dashed (not applied); Decision is where a person acts.
 */
export function DecisionCase({
  found,
  evidence,
  proposed,
  decision,
  record,
  hue,
}: {
  found: ReactNode;
  evidence?: ReactNode;
  proposed?: ReactNode;
  decision: ReactNode;
  record?: ReactNode;
  hue?: Hue;
}) {
  return (
    <PanelRow hue={hue} className="space-y-4">
      <section aria-label="Found">
        <SectionLabel>Found</SectionLabel>
        <div>{found}</div>
      </section>
      {evidence ? (
        <section aria-label="Evidence">
          <SectionLabel>Evidence</SectionLabel>
          {evidence}
        </section>
      ) : null}
      {proposed ? (
        <section aria-label="Proposed by Cadence" className="proposal px-3 py-2.5">
          <p className="mb-1">
            <Tag tone="proposed">Proposed by Cadence</Tag> <span className="text-xs text-prop-ink">Not applied</span>
          </p>
          {proposed}
        </section>
      ) : null}
      <section aria-label="Decision">
        <SectionLabel>Decision</SectionLabel>
        {decision}
      </section>
      {record ? (
        <section aria-label="Record">
          <SectionLabel>Record</SectionLabel>
          {record}
        </section>
      ) : null}
    </PanelRow>
  );
}
