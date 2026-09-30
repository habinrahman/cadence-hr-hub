import { Suspense } from "react";
import { redirect } from "next/navigation";
import { Inbox } from "./inbox/inbox";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  // The backend links to /?document=<id>; that screen now lives at /intake.
  if (typeof params.document === "string") {
    redirect(`/intake?document=${encodeURIComponent(params.document)}`);
  }
  return (
    <Suspense fallback={null}>
      <Inbox />
    </Suspense>
  );
}
