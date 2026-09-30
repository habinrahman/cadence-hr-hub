import { Suspense } from "react";
import { HiringRoute } from "./route-view";

export const metadata = { title: "Requests" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <HiringRoute />
    </Suspense>
  );
}
