import { Suspense } from "react";
import CustomersView from "@/components/CustomersView";

export default function CustomersPage() {
  return <Suspense fallback={<div className="p-6 text-muted">Loading customers…</div>}><CustomersView /></Suspense>;
}
