import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["400", "500", "600", "700"],
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "SyncLayer",
  description:
    "Cross-team intelligence: meetings, repos, slack, tickets — one semantic map.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="bg-surface">
        <Sidebar />
        <div className="md:pl-60 min-h-screen flex flex-col">
          <Topbar />
          <main className="flex-1 px-6 lg:px-8 py-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
