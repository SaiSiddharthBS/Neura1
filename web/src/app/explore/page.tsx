import { Suspense } from "react";
import ExploreView from "@/components/ExploreView";

export default function ExplorePage() {
  return <Suspense fallback={<div className="p-6 text-muted">Opening the graph…</div>}><ExploreView /></Suspense>;
}
