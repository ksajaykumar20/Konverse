"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Plus, Shield, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/admin/tenants", label: "Tenants", icon: Users },
  { href: "/admin/tenants/new", label: "Onboard tenant", icon: Plus },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  async function logout() {
    await fetch("/api/admin/logout", { method: "POST" });
    router.push("/admin/login");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 border-r bg-muted/30 p-4 flex flex-col">
        <div className="px-2 pb-4">
          <div className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Shield className="h-4 w-4" /> Konverse Admin
          </div>
          <div className="mt-1 text-xs text-muted-foreground">Platform operator</div>
        </div>

        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                pathname === href && "bg-accent font-medium text-accent-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>

        <Button
          variant="ghost"
          size="sm"
          onClick={logout}
          className="justify-start gap-2"
        >
          <LogOut className="h-4 w-4" /> Sign out
        </Button>
      </aside>
      <main className="flex-1 p-8">{children}</main>
    </div>
  );
}