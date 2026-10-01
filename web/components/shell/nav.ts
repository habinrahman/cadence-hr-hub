import type { IconName } from "@/components/ui/icons";

export type NavChild = {
  href: string;
  label: string;
  match: (path: string, search: URLSearchParams) => boolean;
  badge?: "reviews";
};

export type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  match: (path: string) => boolean;
  badge?: "decisions" | "reports";
  children?: NavChild[];
};

export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Cadence HR desk",
    items: [
      { href: "/", label: "Command Center", icon: "grid", match: (p) => p === "/" },
      {
        href: "/hiring",
        label: "Hiring Requests",
        icon: "briefcase",
        match: (p) => p.startsWith("/hiring"),
        children: [
          { href: "/hiring", label: "All Requests", match: (p, q) => p.startsWith("/hiring") && !q.get("view") },
          { href: "/hiring?view=processing", label: "New / Processing", match: (p, q) => p.startsWith("/hiring") && q.get("view") === "processing" },
          { href: "/hiring?view=complete", label: "Matching Complete", match: (p, q) => p.startsWith("/hiring") && q.get("view") === "complete" },
        ],
      },
      {
        href: "/candidates",
        label: "Candidates",
        icon: "users",
        match: (p) => ["/candidates", "/merge", "/search", "/source", "/intake", "/data"].some((s) => p.startsWith(s)),
        children: [
          { href: "/candidates", label: "Candidate Intelligence", match: (p) => p.startsWith("/candidates") || p.startsWith("/merge") },
          { href: "/search", label: "Search", match: (p) => p.startsWith("/search") },
          { href: "/source", label: "Source Candidate", match: (p) => p.startsWith("/source") },
          { href: "/intake", label: "CV Intake", match: (p) => p.startsWith("/intake") },
          { href: "/data", label: "Excel Import & Export", match: (p) => p.startsWith("/data") },
        ],
      },
      {
        href: "/queue",
        label: "Review Queue",
        icon: "inbox",
        badge: "decisions",
        match: (p) => p.startsWith("/queue") || p.startsWith("/compare"),
        children: [
          { href: "/queue?type=relationship_review", label: "CV Updates / Duplicates", match: (p, q) => p.startsWith("/compare") || q.get("type") === "relationship_review" },
          { href: "/queue?type=requirement_approval", label: "Requirement Reviews", match: (p, q) => q.get("type") === "requirement_approval" },
          { href: "/queue?type=match_review", label: "Match Reviews", match: (p, q) => q.get("type") === "match_review" },
          { href: "/queue?type=share_approval", label: "Sharing Approvals", match: (p, q) => q.get("type") === "share_approval" },
        ],
      },
    ],
  },
  {
    label: "Oversight",
    items: [
      { href: "/audit", label: "Audit Trail", icon: "shield", match: (p) => p.startsWith("/audit") },
      { href: "/reports", label: "Problem Reports", icon: "alert", match: (p) => p.startsWith("/reports"), badge: "reports" },
    ],
  },
  {
    label: "Setup",
    items: [{ href: "/demo", label: "Set up repository", icon: "upload", match: (p) => p.startsWith("/demo") }],
  },
];

export const ALL_NAV = NAV_GROUPS.flatMap((g) => g.items);

/** Breadcrumb label for the current route. */
export function pageLabel(path: string): string {
  if (path.startsWith("/candidates/")) return "Candidate record";
  if (path.startsWith("/compare")) return "CV comparison";
  if (path.startsWith("/merge")) return "Merge profiles";
  return ALL_NAV.find((item) => item.match(path))?.label ?? "Workspace";
}

export const MOBILE_TABS = [
  { href: "/", label: "Command", match: (p: string) => p === "/" },
  { href: "/candidates", label: "Candidates", match: (p: string) => p.startsWith("/candidates") },
  { href: "/hiring", label: "Requests", match: (p: string) => p.startsWith("/hiring") },
  { href: "/queue", label: "Queue", match: (p: string) => p.startsWith("/queue") || p.startsWith("/compare") },
] as const;
