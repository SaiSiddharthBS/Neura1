import { Suspense } from "react";
import PeopleView from "@/components/PeopleView";

export default function PeoplePage() {
  return (
    <Suspense fallback={<div className="p-6 text-muted">Loading people…</div>}>
      <PeopleView />
    </Suspense>
  );
}
