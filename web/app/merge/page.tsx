import { Suspense } from "react";
import { MergeDesk } from "./form";

export const metadata = { title: "Merge profiles" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <MergeDesk />
    </Suspense>
  );
}
