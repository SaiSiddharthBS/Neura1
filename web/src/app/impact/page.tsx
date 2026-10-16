import { Suspense } from "react";
import ImpactView from "@/components/ImpactView";

type SearchParams = PageProps<"/impact">["searchParams"];

async function Impact({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  return (
    <ImpactView
      source={one(sp.source)}
      item={one(sp.item)}
      price={one(sp.price)}
      lead={one(sp.lead)}
      asOf={one(sp.as_of)}
    />
  );
}

export default function ImpactPage({ searchParams }: PageProps<"/impact">) {
  return (
    <Suspense fallback={<div className="p-6 text-muted">Tracing through the company graph…</div>}>
      <Impact searchParams={searchParams} />
    </Suspense>
  );
}
