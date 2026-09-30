import { Suspense } from "react";
import { CompareView } from "./compare-view";

export const metadata = { title: "CV comparison" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <CompareView />
    </Suspense>
  );
}
