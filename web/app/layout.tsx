import type { Metadata } from "next";
import { Inter, Source_Serif_4, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { ChatDrawer } from "@/components/chat-drawer";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const serif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-serif",
  weight: ["400", "500", "600"],
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
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
    <html
      lang="en"
      className={`${inter.variable} ${serif.variable} ${mono.variable}`}
    >
      <body className="bg-surface">
        <Sidebar />
        <ChatDrawer />
        <div className="md:pl-60 min-h-screen flex flex-col">
          <Topbar />
          <main className="flex-1 px-6 lg:px-8 py-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
