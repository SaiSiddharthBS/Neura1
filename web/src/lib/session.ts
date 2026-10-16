/** The demo passcode and the reviewer's name, remembered in this browser only. */
export function credentials(): { pass: string; name: string } | null {
  let pass = "", name = "";
  try { pass = localStorage.getItem("neura1-passcode") ?? ""; name = localStorage.getItem("neura1-reviewer") ?? ""; } catch {}
  pass = pass || prompt("Demo passcode") || "";
  name = name || prompt("Your name (recorded with the approval)") || "";
  if (!pass || !name) return null;
  try { localStorage.setItem("neura1-passcode", pass); localStorage.setItem("neura1-reviewer", name); } catch {}
  return { pass, name };
}

export function forgetPasscode() {
  try { localStorage.removeItem("neura1-passcode"); } catch {}
}
