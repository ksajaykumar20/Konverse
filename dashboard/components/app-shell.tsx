"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, History, LogOut, MessageSquare, Sparkles } from "lucide-react";

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
    <div className="min-h-screen lg:flex">
      <aside className="flex w-full shrink-0 flex-col border-b border-border/80 bg-white/70 p-4 backdrop-blur lg:min-h-screen lg:w-64 lg:border-b-0 lg:border-r lg:p-5">
        <div className="flex items-center gap-3 px-1 pb-5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm shadow-primary/25">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-semibold tracking-tight">Konverse</div>
            <div className="truncate text-xs text-muted-foreground">{tenant?.name ?? "Loading…"}</div>
          </div>
        </div>

        <div className="mb-5 rounded-lg border border-border/70 bg-muted/45 px-3 py-2.5">
          <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">Workspace</div>
          <div className="mt-1 text-sm font-medium capitalize text-foreground">
            {tenant?.plan ? `${tenant.plan} plan` : "Your knowledge base"}
          </div>
        </div>

        <nav className="flex flex-1 gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className={cn(
              "flex shrink-0 items-center gap-2 rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-all hover:bg-accent hover:text-accent-foreground",
              pathname === href && "bg-primary text-primary-foreground shadow-sm hover:bg-primary hover:text-primary-foreground"
            )}>
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>

        <Button variant="ghost" size="sm" onClick={logout} className="mt-4 justify-start gap-2 border border-transparent hover:border-border lg:mt-0">
          <LogOut className="h-4 w-4" /> Sign out
        </Button>
      </aside>
      <main className="min-w-0 flex-1 p-5 sm:p-8 lg:p-10">{children}</main>
    </div>
  );
}
