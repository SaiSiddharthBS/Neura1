import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Neura1",
  description: "Company brain for hardware companies. Know what a change breaks before it breaks.",
};

const NAV = [
  { href: "/", label: "Inbox" },
  { href: "/brain", label: "Company brain" },
  { href: "/projects", label: "Projects" },
  { href: "/people", label: "People" },
  { href: "/changes", label: "What's new" },
  { href: "/history", label: "Investigations" },
  { href: "/import", label: "Import" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full font-sans">
        <header className="sticky top-0 z-30 border-b border-line bg-panel/90 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-6 px-4">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-ink text-xs text-white">N1</span>
              Neura1
            </Link>
            <nav className="flex gap-1 overflow-x-auto text-sm">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="rounded-md px-3 py-1.5 text-muted hover:bg-bg hover:text-ink">
                  {n.label}
                </Link>
              ))}
            </nav>
            <span className="ml-auto rounded-full border border-warn/30 bg-amber-50 px-2.5 py-0.5 text-xs text-warn">
              Synthetic company: Voltline Controls
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-[1400px] px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
