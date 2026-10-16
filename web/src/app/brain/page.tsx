import { Suspense } from "react";
import BrainView from "@/components/BrainView";

export default function BrainPage() {
  return (
    <Suspense fallback={<div className="p-6 text-muted">Loading the company brain…</div>}>
      <BrainView />
    </Suspense>
  );
}
