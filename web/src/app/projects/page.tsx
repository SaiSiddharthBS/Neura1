import { Suspense } from "react";
import ProjectsView from "@/components/ProjectsView";

export default function ProjectsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-muted">Loading projects…</div>}>
      <ProjectsView />
    </Suspense>
  );
}
