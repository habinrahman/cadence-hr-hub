import { redirect } from "next/navigation";
import { CommandCenter } from "./command/command-center";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  // The backend links to /?document=<id>; that screen lives at /intake.
  if (typeof params.document === "string") {
    redirect(`/intake?document=${encodeURIComponent(params.document)}`);
  }
  // The old inbox filter moved to the review queue.
  if (typeof params.type === "string") {
    redirect(`/queue?type=${encodeURIComponent(params.type)}`);
  }
  return <CommandCenter />;
}
