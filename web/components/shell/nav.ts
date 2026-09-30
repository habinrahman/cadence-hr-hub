export const PRIMARY_NAV = [
  { href: "/", label: "Inbox", match: (p: string) => p === "/" },
  { href: "/hiring", label: "Requests", match: (p: string) => p.startsWith("/hiring") },
  { href: "/candidates", label: "Candidates", match: (p: string) => p.startsWith("/candidates") },
  { href: "/intake", label: "Intake", match: (p: string) => p.startsWith("/intake") },
] as const;

export const ADD_ITEMS = [
  { href: "/intake", label: "Upload a CV" },
  { href: "/source", label: "Source a candidate" },
  { href: "/data", label: "Import an Excel list" },
  { href: "/hiring?new=1", label: "New hiring request" },
] as const;

export const DESK_ITEMS = [
  { href: "/reports", label: "Problem reports" },
  { href: "/data#export", label: "Hiring-activity export" },
  { href: "/merge", label: "Merge two profiles" },
] as const;
