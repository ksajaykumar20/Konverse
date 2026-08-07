"use client";

import { useState } from "react";
import Link from "next/link";

import { adminApi } from "@/lib/admin-api";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { KeyReveal } from "@/components/key-reveal";
import { Spinner } from "@/components/ui/spinner";

export default function OnboardTenant() {
  const [form, setForm] = useState({
    name: "",
    slug: "",
    industry: "",
    rate_limit_plan: "free",
    system_prompt: "",
  });
  const [createdKey, setCreatedKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await adminApi.createTenant({
        name: form.name,
        slug: form.slug || undefined,
        industry: form.industry,
        rate_limit_plan: form.rate_limit_plan,
        system_prompt: form.system_prompt || undefined,
      });
      setCreatedKey(res.api_key); // shown exactly once
    } catch (e: any) {
      setError(e.message ?? "Failed to create tenant");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto grid gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Onboard tenant</h1>
        <p className="text-sm text-muted-foreground">
          Create a tenant and get its API key. The key is shown exactly once.
        </p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={submit} className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="name">Tenant name *</Label>
              <Input id="name" value={form.name} onChange={(e) => set("name", e.target.value)} required />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="slug">Slug (optional)</Label>
              <Input id="slug" value={form.slug} onChange={(e) => set("slug", e.target.value)} placeholder="auto-generated if blank" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="industry">Industry</Label>
              <Input id="industry" value={form.industry} onChange={(e) => set("industry", e.target.value)} placeholder="e.g. retail, healthcare, banking" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="plan">Rate-limit plan</Label>
              <select
                id="plan"
                value={form.rate_limit_plan}
                onChange={(e) => set("rate_limit_plan", e.target.value)}
                className="h-9 rounded-md border bg-background px-3 text-sm"
              >
                <option value="free">free</option>
                <option value="pro">pro</option>
                <option value="enterprise">enterprise</option>
              </select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="system_prompt">System prompt (optional)</Label>
              <Textarea
                id="system_prompt"
                value={form.system_prompt}
                onChange={(e) => set("system_prompt", e.target.value)}
                rows={3}
                placeholder="Additional guidance prepended to retrieval context during chat."
              />
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button type="submit" disabled={busy || !form.name}>
              {busy ? <Spinner /> : "Create tenant"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Link
        href="/admin/tenants"
        className={buttonVariants({ variant: "outline", size: "sm" })}
      >
        Back to tenants
      </Link>

      <KeyReveal title="New tenant API key" value={createdKey} onClose={() => setCreatedKey("")} />
    </div>
  );
}