"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, History, LogOut, MessageSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTenant } from "@/lib/tenant-context";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/sessions", label: "Sessions", icon: History },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { tenant, logout } = useTenant();
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 border-r bg-muted/30 p-4 flex flex-col">
        <div className="px-2 pb-4">
          <div className="text-lg font-semibold tracking-tight">Konverse</div>
          <div className="mt-1 truncate text-xs text-muted-foreground">
            {tenant?.name ?? "…"}
          </div>
          {tenant?.plan && (
            <div className="text-xs capitalize text-muted-foreground">
              plan · {tenant.plan}
            </div>
          )}
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