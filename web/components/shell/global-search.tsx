"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState, type RefObject } from "react";
import { listHiringRequests, searchCandidates, type RequestSummary } from "@/lib/api";
import { relativeAge } from "@/lib/format";
import { PHASE, requestPhase } from "@/lib/request-phase";
import { groupHits, type CandidateGroup } from "@/lib/search-state";
import { Avatar } from "@/components/ui/avatar";
import { Icon } from "@/components/ui/icons";

const MIN_CHARS = 2;
const PAUSE_MS = 300;

/** The search list only has the processing stage; once matching is done, the match count says more than "open". */
function stageText(r: RequestSummary): string {
  const phase = requestPhase(r.processing);
  return phase ? PHASE[phase].label : `${r.matched_count} matched`;
}

type Item = { key: string; href: string; kind: "request" | "candidate" | "all"; label: string; sub: string; name?: string | null };

function requestsMatching(all: RequestSummary[], q: string): RequestSummary[] {
  const needle = q.trim().toLowerCase();
  return all.filter((r) => `${r.job_title} ${r.company}`.toLowerCase().includes(needle)).slice(0, 4);
}

function passage(group: CandidateGroup): string {
  const first = (group.hits.find((h) => h.evidence)?.evidence ?? "").replace(/\s+/g, " ").trim();
  // The backend cuts its window mid-word. Start at the next whole word.
  const whole = /^[\p{L}\p{N}]/u.test(first) && first.includes(" ") && !/^[A-Z]/.test(first) ? first.slice(first.indexOf(" ") + 1) : first;
  return whole.slice(0, 90);
}

/** Header search. Candidates come from the existing /search, hiring requests from the existing request list. */
export function GlobalSearch({ inputRef, autoFocus = false, onDone }: { inputRef?: RefObject<HTMLInputElement | null>; autoFocus?: boolean; onDone?: () => void }) {
  const router = useRouter();
  const uid = useId();
  const box = useRef<HTMLDivElement>(null);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [groups, setGroups] = useState<CandidateGroup[]>([]);
  const [requests, setRequests] = useState<RequestSummary[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const run = useRef(0);
  const term = q.trim();
  const ready = term.length >= MIN_CHARS;

  // The request list is small and already public to the desk, so fetch it once, on first use.
  function warm() {
    if (requests !== null) return;
    listHiringRequests()
      .then((r) => setRequests(r.requests))
      .catch(() => setRequests([]));
  }

  useEffect(() => {
    if (!ready) {
      run.current++;
      setGroups([]);
      setBusy(false);
      setFailed(false);
      return;
    }
    const id = ++run.current;
    setBusy(true);
    const timer = setTimeout(() => {
      searchCandidates({ q: term })
        .then((payload) => {
          if (id !== run.current) return;
          setGroups(groupHits(payload.results).slice(0, 5));
          setFailed(false);
        })
        .catch(() => {
          if (id !== run.current) return;
          setGroups([]);
          setFailed(true);
        })
        .finally(() => {
          if (id === run.current) setBusy(false);
        });
    }, PAUSE_MS);
    return () => clearTimeout(timer);
  }, [term, ready]);

  useEffect(() => {
    const away = (event: PointerEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, []);

  const items = useMemo<Item[]>(() => {
    if (!ready) return [];
    const list: Item[] = [];
    for (const r of requests ? requestsMatching(requests, term) : []) {
      list.push({
        key: `r-${r.id}`,
        href: `/hiring?request=${r.id}`,
        kind: "request",
        label: r.job_title,
        sub: `${r.company} · ${stageText(r)} · ${relativeAge(r.received_at)}`,
      });
    }
    for (const g of groups) {
      if (!g.candidateId) continue;
      list.push({ key: `c-${g.key}`, href: `/candidates/${g.candidateId}`, kind: "candidate", label: g.name ?? "Unnamed candidate", sub: passage(g), name: g.name });
    }
    list.push({ key: "all", href: `/candidates?q=${encodeURIComponent(term)}`, kind: "all", label: `See all candidate results for “${term}”`, sub: "" });
    return list;
  }, [ready, requests, groups, term]);

  function go(item: Item) {
    setOpen(false);
    setQ("");
    onDone?.();
    router.push(item.href);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      if (open) event.preventDefault();
      setOpen(false);
      setActive(-1);
      if (!open) onDone?.();
    } else if (event.key === "ArrowDown" && items.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % items.length);
    } else if (event.key === "ArrowUp" && items.length > 0) {
      event.preventDefault();
      setActive((i) => (i <= 0 ? items.length - 1 : i - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (active >= 0 && items[active]) go(items[active]);
      else if (term) go({ key: "all", href: `/candidates?q=${encodeURIComponent(term)}`, kind: "all", label: "", sub: "" });
    }
  }

  const listId = `${uid}-list`;
  const showPanel = open && ready;
  const requestItems = items.filter((i) => i.kind === "request");
  const candidateItems = items.filter((i) => i.kind === "candidate");
  const allItem = items.find((i) => i.kind === "all");

  function row(item: Item) {
    const index = items.indexOf(item);
    return (
      <li
        key={item.key}
        id={`${uid}-o${index}`}
        role="option"
        aria-selected={index === active}
        onMouseEnter={() => setActive(index)}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => go(item)}
        className={`flex min-h-11 cursor-pointer items-center gap-3 px-4 py-2 sm:min-h-10 ${index === active ? "bg-inset" : ""}`}
      >
        {item.kind === "candidate" ? <Avatar name={item.name ?? null} size={28} /> : <Icon name={item.kind === "all" ? "search" : "briefcase"} size={16} className="shrink-0 text-mut" />}
        <span className="min-w-0 flex-1">
          <span className={`block truncate text-[13.5px] ${item.kind === "all" ? "font-semibold text-human-ink" : "font-semibold"}`}>{item.label}</span>
          {item.sub ? <span className="block truncate text-[12px] text-mut">{item.sub}</span> : null}
        </span>
      </li>
    );
  }

  return (
    <div ref={box} className="relative w-full">
      <div className="flex w-full items-center gap-2 border-b border-rule-strong/40 pb-1.5 focus-within:border-human">
        <Icon name="search" size={16} className="text-mut" />
        <label htmlFor={`${uid}-input`} className="sr-only">
          Search candidates, roles, requests
        </label>
        <input
          ref={inputRef}
          id={`${uid}-input`}
          type="search"
          role="combobox"
          aria-expanded={showPanel}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showPanel && active >= 0 ? `${uid}-o${active}` : undefined}
          autoComplete="off"
          autoFocus={autoFocus}
          value={q}
          placeholder="Search candidates, roles, requests"
          className="w-full bg-transparent text-[14px] text-ink outline-none placeholder:text-mut [&::-webkit-search-cancel-button]:hidden"
          onFocus={() => {
            warm();
            setOpen(true);
          }}
          onChange={(event) => {
            setQ(event.target.value);
            setOpen(true);
            setActive(-1);
            warm();
          }}
          onKeyDown={onKeyDown}
        />
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        {showPanel && !busy ? `${candidateItems.length} candidates, ${requestItems.length} hiring requests` : ""}
      </p>

      {showPanel ? (
        <div className="absolute left-0 right-0 top-full z-40 mt-2 max-h-[70dvh] min-w-[22rem] overflow-y-auto border border-rule bg-panel shadow-[0_8px_24px_rgba(17,28,50,0.12)] md:left-auto md:w-[26rem]">
          <ul id={listId} role="listbox" aria-label="Search results">
            {requestItems.length > 0 ? (
              <li role="presentation">
                <p className="border-b border-rule bg-inset px-4 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mut">Hiring requests</p>
                <ul role="group" aria-label="Hiring requests">{requestItems.map(row)}</ul>
              </li>
            ) : null}
            {candidateItems.length > 0 ? (
              <li role="presentation">
                <p className="border-y border-rule bg-inset px-4 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mut">Candidates</p>
                <ul role="group" aria-label="Candidates">{candidateItems.map(row)}</ul>
              </li>
            ) : null}
            {allItem ? <li role="presentation" className="border-t border-rule"><ul role="group">{row(allItem)}</ul></li> : null}
          </ul>
          <p className="border-t border-rule px-4 py-2 text-[12px] text-mut" aria-live="polite">
            {failed
              ? "Candidate search is unavailable right now. Requests are still listed."
              : busy
                ? "Searching…"
                : candidateItems.length === 0 && requestItems.length === 0
                  ? "No candidate passages or requests match."
                  : "Opening a candidate record is written to the audit trail."}
          </p>
        </div>
      ) : null}
    </div>
  );
}
