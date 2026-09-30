import { Suspense } from "react";
import { Intake } from "./intake";

export const metadata = { title: "Intake" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <Intake />
    </Suspense>
  );
}
