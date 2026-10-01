import type { SVGProps } from "react";

/** A small line-icon set for the shell and pages. Decorative: every icon sits next to visible text. */
const PATHS = {
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  users: "M16 20v-1.5A3.5 3.5 0 0 0 12.5 15h-5A3.5 3.5 0 0 0 4 18.5V20M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M20 20v-1.5a3.5 3.5 0 0 0-2.5-3.35M15.5 4.15a3.5 3.5 0 0 1 0 6.7",
  briefcase: "M4 8h16v11H4zM9 8V6a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 6v2M4 13h16",
  upload: "M12 15V4M7.5 8.5 12 4l4.5 4.5M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15",
  inbox: "M4 13h4.5l1.5 2.5h4l1.5-2.5H20M4 13l2.5-7.5h11L20 13v5.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5z",
  shield: "M12 3.5 19 6v5.5c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6zM9 12l2 2 4-4",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14M20 20l-4-4",
  bell: "M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15zM10 20.5h4",
  arrowUpRight: "M8 16 16 8M9 8h7v7",
  mail: "M4 6h16v12H4zM4 7l8 6 8-6",
  phone: "M8.5 4h-3A1.5 1.5 0 0 0 4 5.6 14.5 14.5 0 0 0 18.4 20a1.5 1.5 0 0 0 1.6-1.5v-3l-3.5-1.5-2 2a10 10 0 0 1-4.5-4.5l2-2z",
  pin: "M12 21s-6.5-5.7-6.5-11a6.5 6.5 0 0 1 13 0c0 5.3-6.5 11-6.5 11M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5",
  clock: "M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17M12 7.5V12l3 2",
  paperclip: "M16.5 7.5 9 15a2.1 2.1 0 0 1-3-3l8-8a3.5 3.5 0 0 1 5 5l-8.5 8.5a5 5 0 0 1-7-7L11 3",
  cap: "M2.5 9 12 4.5 21.5 9 12 13.5zM6.5 11v4.5c0 1.5 2.5 3 5.5 3s5.5-1.5 5.5-3V11",
  file: "M6 3.5h8l4 4v13H6zM14 3.5v4h4M9 12h6M9 15.5h6",
  compare: "M8 4v16M16 4v16M4 8h4M16 16h4M4 12h4M16 12h4",
  alert: "M12 4 21 19.5H3zM12 10v4M12 17h.01",
  table: "M4 5h16v14H4zM4 10h16M4 14.5h16M10 5v14",
  merge: "M7 4v5a5 5 0 0 0 5 5h5M7 20v-6M14 11l3 3-3 3",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3A4 4 0 0 0 13 5.3l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6 6 18",
  check: "M5 12.5 10 17 19 7",
  plus: "M12 5v14M5 12h14",
  filter: "M4 6h16M7 12h10M10 18h4",
  chevronDown: "M6 9l6 6 6-6",
  download: "M12 4v11M7.5 10.5 12 15l4.5-4.5M4 19.5h16",
  activity: "M3 12h4l3-7 4 14 3-7h4",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, className = "", ...rest }: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
