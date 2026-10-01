"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { searchCandidates, type SearchHit } from "@/lib/api";
import { FILTERS, groupHits, hasCriteria, parseSearch, toQueryString } from "@/lib/search-state";
import { plural } from "@/lib/format";
import { Button, LinkButton } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Field, inputClass } from "@/components/ui/field";
import { Icon } from "@/components/ui/icons";
import { PageHeader, Panel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Directory } from "./directory";
import { ResultGroup } from "./result-group";

const EXAMPLES = [
  { label: "Python and PostgreSQL", href: "/candidates?q=python+postgresql" },
  { label: "Chartered accountant, 5+ years", href: "/candidates?certificate=chartered&min_years=5" },
  { label: "Project manager in construction", href: "/candidates?job_title=project+manager&industry=construction" },
];

export function Search() {
  const router = useRouter();
  const params = useSearchParams();
  const applied = useMemo(() => parseSearch(new URLSearchParams(params.toString())), [params]);
  const [draft, setDraft] = useState<Record<string, string>>(applied);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const runId = useRef(0);

  // Keep the form in step with the URL, then search whenever the URL carries criteria.
  const key = toQueryString(applied);
  useEffect(() => {
    setDraft(applied);
    if (!hasCriteria(applied)) {
      setHits(null);
      setError(null);
      return;
    }
    const id = ++runId.current;
    setBusy(true);
    setError(null);
    searchCandidates(applied)
      .then((payload) => {
        if (id === runId.current) setHits(payload.results);
      })
      .catch((reason) => {
        if (id === runId.current) {
          setHits(null);
          setError(reason);
        }
      })
      .finally(() => {
        if (id === runId.current) setBusy(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const groups = useMemo(() => (hits ? groupHits(hits) : []), [hits]);
  const activeFilters = FILTERS.filter((f) => f.name in draft);
  const available = FILTERS.filter((f) => !(f.name in draft));
  const highlight = [applied.q ?? "", applied.skill ?? ""].join(" ");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const qs = toQueryString(draft);
    router.replace(qs ? `/candidates?${qs}` : "/candidates");
  }

  function remove(name: string) {
    const next = { ...draft };
    delete next[name];
    setDraft(next);
    const qs = toQueryString(next);
    router.replace(qs ? `/candidates?${qs}` : "/candidates");
  }

  return (
    <>
      <PageHeader
        eyebrow="Candidate workspace"
        title="Candidate intelligence"
        sub="Browse every confirmed profile, or search inside the CVs. Each search result shows who matched, why, and the passage that says so."
        actions={
          <LinkButton variant="primary" size="lg" href="/intake">
            Import CVs <Icon name="upload" size={16} />
          </LinkButton>
        }
      />

      <form onSubmit={submit} role="search" aria-label="Candidate search" className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex min-h-11 min-w-0 flex-1 basis-80 items-center gap-2.5 border border-rule-strong/60 bg-panel px-3.5 focus-within:border-human sm:max-w-[34rem]">
            <Icon name="search" size={17} className="text-mut" />
            <label htmlFor="q" className="sr-only">
              Words in the CV
            </label>
            <input
              id="q"
              value={draft.q ?? ""}
              placeholder="Search candidates, skills, or roles"
              className="min-h-10 w-full bg-transparent text-[14px] outline-none placeholder:text-mut"
              onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            />
          </div>
          <Button type="submit" variant="primary" size="lg" busy={busy}>
            Search
          </Button>
        </div>

        <div className="mt-3.5 flex flex-wrap items-center gap-2" role="group" aria-label="Add a filter">
          <span className="mr-1 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mut">
            <Icon name="filter" size={14} /> Filters
          </span>
          {available.map((f) => (
            <button
              key={f.name}
              type="button"
              onClick={() => setDraft({ ...draft, [f.name]: draft[f.name] ?? " " })}
              className="inline-flex min-h-11 items-center gap-1.5 border border-rule bg-panel px-3 text-[13px] text-ink hover:border-rule-strong sm:min-h-8"
            >
              {f.label}
              <Icon name="plus" size={13} className="text-mut" />
            </button>
          ))}
        </div>

        {activeFilters.length > 0 ? (
          <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {activeFilters.map((f) => (
              <div key={f.name} className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <Field label={f.label} hint={f.note}>
                    {({ id, describedBy }) => (
                      <input
                        id={id}
                        aria-describedby={describedBy}
                        className={inputClass}
                        inputMode={f.name === "min_years" ? "decimal" : undefined}
                        value={draft[f.name] ?? ""}
                        onChange={(event) => setDraft({ ...draft, [f.name]: event.target.value })}
                      />
                    )}
                  </Field>
                </div>
                <Button aria-label={`Remove the ${f.label} filter`} onClick={() => remove(f.name)}>
                  Remove
                </Button>
              </div>
            ))}
          </div>
        ) : null}
        <p className="mt-3 text-[12.5px] text-mut">
          Filters combine with AND. Only confirmed profiles are searched. Nationality searches words already written in the CV.
        </p>
      </form>

      {Object.keys(applied).length > 0 ? (
        <p className="mb-3 flex flex-wrap items-center gap-1.5" aria-label="Active criteria">
          {Object.entries(applied).map(([name, value]) => (
            <Chip key={name} onRemove={() => remove(name)} removeLabel={`Remove ${name === "q" ? "words" : name} criterion`}>
              <span className="text-mut">{name === "q" ? "Words" : (FILTERS.find((f) => f.name === name)?.label ?? name)}:</span> {value}
            </Chip>
          ))}
        </p>
      ) : null}

      <p role="status" aria-live="polite" className="sr-only">
        {busy ? "Searching" : hits ? `${plural(groups.length, "candidate")} found` : ""}
      </p>

      {error ? <ErrorState error={error} onRetry={() => router.refresh()} /> : null}

      {busy ? (
        <div aria-busy="true">
          <PanelSkeleton rows={3} />
        </div>
      ) : null}

      {!busy && !error && !hasCriteria(applied) ? (
        <div className="space-y-5">
          <p className="flex flex-wrap items-center gap-2 text-[13px] text-mut">
            <span className="font-mono text-[11px] uppercase tracking-[0.12em]">Try</span>
            {EXAMPLES.map((e) => (
              <Link
                key={e.href}
                href={e.href}
                prefetch={false}
                className="inline-flex min-h-11 items-center border border-rule bg-panel px-3 text-[13px] text-ink no-underline hover:border-rule-strong sm:min-h-8"
              >
                {e.label}
              </Link>
            ))}
          </p>
          <Directory />
        </div>
      ) : null}

      {!busy && !error && hits !== null && hasCriteria(applied) ? (
        groups.length === 0 ? (
          <EmptyState title="No matches" body="Nothing in the confirmed CVs fits every criterion. Remove the most specific filter and try again." />
        ) : (
          <section aria-label="Results">
            <Panel>
              <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule px-5 py-3.5">
                <p className="text-[14px]">
                  <span className="text-[18px] font-semibold">{groups.length}</span>{" "}
                  <span className="text-mut">
                    {groups.length === 1 ? "candidate" : "candidates"} · {plural(hits.length, "passage")}
                  </span>
                </p>
                <p className="text-[12.5px] text-human-ink">Ordered by relevance (no score shown)</p>
              </div>
              <div
                aria-hidden="true"
                className="hidden grid-cols-[17rem_minmax(0,17rem)_minmax(0,1fr)_2rem] gap-6 border-b border-rule bg-inset px-5 py-2.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mut xl:grid"
              >
                <span>Candidate</span>
                <span>Why it matched</span>
                <span>Evidence</span>
                <span />
              </div>
              <ul>
                {groups.map((g) => (
                  <ResultGroup key={g.key} group={g} highlight={highlight} />
                ))}
              </ul>
            </Panel>
          </section>
        )
      ) : null}
    </>
  );
}
