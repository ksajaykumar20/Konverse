"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, KeyRound, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";

export default function LoginPage() {
  const router = useRouter();
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ apiKey }) });
      if (response.ok) { router.replace("/documents"); router.refresh(); return; }
      const data = await response.json().catch(() => ({}));
      setError(data.error ?? "Login failed");
    } catch { setError("Could not reach the dashboard API"); } finally { setBusy(false); }
  }

  return (
    <main className="grid min-h-screen overflow-hidden bg-background lg:grid-cols-[1.1fr_0.9fr]">
      <section className="relative hidden overflow-hidden bg-foreground p-12 text-background lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3 text-lg font-semibold"><span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground"><Sparkles className="h-4 w-4" /></span> Konverse</div>
        <div className="relative max-w-md"><p className="mb-5 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Knowledge, made useful</p><h1 className="text-5xl font-semibold leading-[1.08] tracking-tight">A calmer way to work with what your team knows.</h1><p className="mt-6 max-w-sm text-base leading-7 text-background/65">Upload your material and let a grounded assistant help your team find answers faster.</p></div>
        <p className="text-sm text-background/45">Your workspace is private to your organization.</p>
        <div className="absolute -right-24 top-24 h-80 w-80 rounded-full bg-primary/30 blur-3xl" />
        <div className="absolute -bottom-36 left-24 h-72 w-72 rounded-full border border-background/10" />
      </section>

      <section className="grid place-items-center p-5 sm:p-10">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden"><span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground"><Sparkles className="h-4 w-4" /></span><span className="text-lg font-semibold">Konverse</span></div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Welcome back</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight">Sign in to your workspace</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">Use the API key issued for your organization.</p>
          <Card className="mt-7 border-border/80 bg-white/80 shadow-lg shadow-slate-900/5"><CardContent className="p-6"><form onSubmit={submit} className="space-y-5"><div className="space-y-2"><Label htmlFor="apikey">API key</Label><div className="relative"><KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input id="apikey" type="password" autoComplete="off" placeholder="sk_..." className="pl-10" value={apiKey} onChange={(event) => setApiKey(event.target.value)} required /></div></div>{error && <p className="text-sm text-destructive">{error}</p>}<Button type="submit" className="w-full" disabled={busy || !apiKey}>{busy ? <Spinner /> : <>Continue <ArrowRight className="h-4 w-4" /></>}</Button></form></CardContent></Card>
        </div>
      </section>
    </main>
  );
}
