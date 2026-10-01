const TINTS = [
  "bg-t-rel-bg text-t-rel-ink",
  "bg-t-req-bg text-t-req-ink",
  "bg-t-match-bg text-t-match-ink",
  "bg-t-share-bg text-t-share-ink",
  "bg-prop-bg text-prop-ink",
];

function initials(name: string | null): string {
  const words = (name ?? "").split(/\s+/).filter((w) => /^[\p{L}]/u.test(w));
  if (words.length === 0) return "?";
  return (words[0][0] + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
}

/** Two-letter initials in a tinted square. The tint is picked from the name so it stays the same for the same person. */
export function Avatar({ name, size = 32 }: { name: string | null; size?: number }) {
  let hash = 0;
  for (const ch of name ?? "") hash = (hash * 31 + ch.charCodeAt(0)) % 997;
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size }}
      className={`inline-flex shrink-0 items-center justify-center rounded-[2px] font-mono text-[11px] font-medium ${TINTS[hash % TINTS.length]}`}
    >
      {initials(name)}
    </span>
  );
}
