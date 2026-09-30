import { CandidateView } from "./view";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CandidateView id={id} />;
}
