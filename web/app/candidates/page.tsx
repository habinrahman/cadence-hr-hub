import { Suspense } from "react";
import { Search } from "./search";

export const metadata = { title: "Candidates" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <Search />
    </Suspense>
  );
}
