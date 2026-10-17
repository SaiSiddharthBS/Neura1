/** Who is making a change, for the record. The demo needs no passcode; a deployment can require one again by setting
 *  NEURA1_DEMO_PASSCODE on the server, and then the app asks for it the first time a change is refused. */

export function storedPasscode(): string {
  try { return localStorage.getItem("neura1-passcode") ?? ""; } catch { return ""; }
}

/** The name recorded with an approval or a change: the person the app is acting for. */
export function reviewerName(): string {
  try {
    return localStorage.getItem("neura1-viewer-name") || localStorage.getItem("neura1-reviewer") || "Demo visitor";
  } catch {
    return "Demo visitor";
  }
}

export function credentials(): { pass: string; name: string } {
  return { pass: storedPasscode(), name: reviewerName() };
}

/** Only when the server says a passcode is required. */
export function askPasscode(): string | null {
  const p = typeof window !== "undefined" ? window.prompt("This deployment needs a passcode for changes") : null;
  if (p) { try { localStorage.setItem("neura1-passcode", p); } catch { /* kept for this request only */ } }
  return p || null;
}

export function forgetPasscode() {
  try { localStorage.removeItem("neura1-passcode"); } catch { /* nothing stored */ }
}
