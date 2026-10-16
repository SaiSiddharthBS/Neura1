import { Suspense } from "react";
import DocsHome from "@/components/docs/DocsHome";

export default function DocsPage() {
  return <Suspense fallback={<div className="p-6 text-muted">Opening documents…</div>}><DocsHome /></Suspense>;
}
