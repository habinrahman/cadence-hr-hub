import type { DocumentSummary } from "@/lib/api";
import { DOCUMENT_STATUS } from "@/lib/labels";
import { shortDate } from "@/lib/format";
import { Tag } from "@/components/ui/tag";

export function FileList({
  documents,
  selectedId,
  onSelect,
}: {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (documents.length === 0) return <p className="px-3 py-6 text-mut">No files yet. Upload a CV to start.</p>;
  return (
    <ul className="max-h-72 divide-y divide-rule overflow-y-auto lg:max-h-[70vh]">
      {documents.map((item) => {
        const status = DOCUMENT_STATUS[item.status] ?? { label: item.status, tone: "neutral" as const, note: "" };
        const selected = item.id === selectedId;
        return (
          <li key={item.id}>
            <button
              type="button"
              aria-current={selected ? "true" : undefined}
              onClick={() => onSelect(item.id)}
              className={`block min-h-11 w-full px-3 py-2 text-left ${selected ? "bg-human-bg" : "hover:bg-inset"}`}
            >
              <span title={item.original_filename} className="block truncate font-mono text-[13px] font-semibold">
                {item.original_filename}
              </span>
              <span className="mt-0.5 flex items-center gap-2 text-xs text-mut">
                <Tag tone={status.tone}>{status.label}</Tag>
                {shortDate(item.received_at)}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
