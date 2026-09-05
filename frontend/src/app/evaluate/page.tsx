import { MerchantRequestPanel } from "@/components/Request";
import { Rule, Shell } from "@/components/ui";

export default function EvaluatePage() {
  return (
    <Shell className="pt-14 pb-16">
      <p className="eyebrow">Merchant workflow</p>
      <h1 className="t-headline mt-4 text-ink">EVALUATE A PROMOTION</h1>
      <p className="t-lead mt-4 max-w-[54ch] text-ink-muted">
        State the promotion you want to run and let MarginPilot price the
        economics.
      </p>
      <Rule className="mt-10" />
      <div className="pt-10">
        <MerchantRequestPanel />
      </div>
    </Shell>
  );
}
