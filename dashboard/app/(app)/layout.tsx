import { AppShell } from "@/components/app-shell";
import { TenantProvider } from "@/lib/tenant-context";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <TenantProvider>
      <AppShell>{children}</AppShell>
    </TenantProvider>
  );
}