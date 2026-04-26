import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <Sidebar />
      <div className="md:pl-60 min-h-screen flex flex-col">
        <Topbar />
        <main className="flex-1 px-6 lg:px-8 py-8">{children}</main>
      </div>
    </>
  );
}
