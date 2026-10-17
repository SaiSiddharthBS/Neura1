export type Member = { id: string; name: string; online: boolean };
export type Conversation = {
  id: string; name: string; purpose: string | null; kind: "channel" | "group" | "dm";
  members: Member[]; created_by: string | null; default: boolean; created_at: string | null;
  messages: number; last: string | null; unread: number; mentions: number;
  preview: { author: string; mine: boolean; text: string; kind: string } | null;
};
export type Msg = {
  id: string; text: string; author: string; author_id: string | null; ts: string; kind: string;
  sources: string | null; links: string | null; reply_to: string | null; edited_at: string | null; deleted: boolean;
  reactions: Record<string, string[]>; about: { id: string; label: string; name: string }[];
  reply: { id: string; author: string | null; text: string; deleted: boolean } | null;
};
export type Thread = { messages: Msg[]; cursor: string; typing: string[]; read: Record<string, string> };
export type Person = { id: string; name: string; role: string; team: string };
export type Hit = Msg & { channel: string; channel_name: string; kind_of_channel: Conversation["kind"] };

export const REACTIONS = ["👍", "❤️", "😂", "🎉", "👀", "✅", "🙏", "🔥"];
export const BOT = "Neura1";

/** "10:42" today, "Yesterday", "Mon" this week, then "12 Oct". */
export function when(ts: string | null): string {
  if (!ts) return "";
  const d = new Date(ts), now = new Date();
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff === 0) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diff === 1) return "Yesterday";
  if (diff < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

export function dayLabel(ts: string): string {
  const d = new Date(ts), now = new Date();
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}

export function time(ts: string): string {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function parseJson<T>(s: string | null, fallback: T): T {
  if (!s) return fallback;
  try { return JSON.parse(s) as T; } catch { return fallback; }
}
