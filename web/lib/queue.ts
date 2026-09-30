import type { DeskItem } from "@/lib/api";

export type QueueItem = DeskItem;
export type QueueGroup = {
  key: string;
  type: string;
  subject: string;
  names: string[];
  count: number;
  status: string;
  created_at: string;
  href: string;
  requestId: string | null;
};

export function requestIdFromHref(href: string): string | null {
  const query = href.split("?")[1];
  if (!query) return null;
  return new URLSearchParams(query).get("request");
}

/** The server emits one row per proposed requirement and per match. Group those by request. */
const GROUPED = new Set(["requirement_approval", "match_review"]);

export function groupQueue(items: QueueItem[]): QueueGroup[] {
  const groups = new Map<string, QueueGroup>();
  items.forEach((item, index) => {
    const requestId = requestIdFromHref(item.href);
    const grouped = GROUPED.has(item.type) && requestId !== null;
    const key = grouped ? `${item.type}:${requestId}` : `${item.type}:${item.href}:${index}`;
    let subject = item.subject;
    const names: string[] = [];
    if (grouped && item.type === "match_review") {
      const cut = item.subject.indexOf(" · ");
      if (cut > 0) {
        names.push(item.subject.slice(0, cut));
        subject = item.subject.slice(cut + 3);
      }
    }
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, {
        key,
        type: item.type,
        subject,
        names,
        count: 1,
        status: item.status,
        created_at: item.created_at,
        href: item.href,
        requestId,
      });
      return;
    }
    existing.count += 1;
    existing.names.push(...names);
    if (item.created_at > existing.created_at) existing.created_at = item.created_at;
  });
  return [...groups.values()].sort((a, b) =>
    a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0,
  );
}
