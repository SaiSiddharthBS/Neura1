import type { Metadata } from "next";
import { Inter } from "next/font/google";
import AppShell from "@/components/AppShell";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Neura1",
  description: "Company brain for hardware companies. Know what a change breaks before it breaks.",
  icons: { icon: "/mark.png" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full font-sans">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
