import { Suspense } from "react";
import { ReviewQueue } from "./queue";

export const metadata = { title: "Review queue" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ReviewQueue />
    </Suspense>
  );
}
