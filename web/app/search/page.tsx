import { redirect } from "next/navigation";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(await searchParams)) {
    if (typeof value === "string") params.set(name, value);
  }
  const query = params.toString();
  redirect(query ? `/candidates?${query}` : "/candidates");
}
