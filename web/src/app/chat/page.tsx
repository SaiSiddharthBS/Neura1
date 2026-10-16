import { Suspense } from "react";
import ChatView from "@/components/ChatView";

export default function ChatPage() {
  return <Suspense fallback={<div className="p-6 text-muted">Opening chat…</div>}><ChatView /></Suspense>;
}
