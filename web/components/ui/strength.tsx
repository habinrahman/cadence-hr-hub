/** Mandatory requirements can exclude a candidate; preferred ones cannot. The two never look alike. */
export function StrengthTag({ strength }: { strength: string }) {
  const mandatory = strength === "mandatory";
  return (
    <span
      className={`inline-block rounded-[2px] px-1.5 py-px font-mono text-[10.5px] font-medium uppercase leading-[1.6] tracking-[0.08em] ${
        mandatory ? "border border-ink bg-ink text-white" : "border border-rule-strong/60 bg-panel text-mut"
      }`}
    >
      {mandatory ? "Mandatory" : "Preferred"}
    </span>
  );
}
