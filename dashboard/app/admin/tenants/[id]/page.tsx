"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { adminApi } from "@/lib/admin-api";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { KeyReveal } from "@/components/key-reveal";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

type Tenant = {
  id: string;
  name: string;
  slug: string;
  industry: string;
  rate_limit_plan: string;
  is_active: boolean;
  system_prompt: string;
  guardrail_rules: Record<string, any>;
  document_count: number;
  session_count: number;
  message_count: number;
  created_at: string;
};

export default function TenantDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [tab, setTab] = useState<"docs" | "sessions">("docs");
  const [form, setForm] = useState({ plan: "", industry: "", system_prompt: "", guardrail_rules: "" });
  const [revealedKey, setRevealedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const t = await adminApi.getTenant(id);
      setTenant(t);
      setForm({
        plan: t.rate_limit_plan,
        industry: t.industry,
        system_prompt: t.system_prompt ?? "",
        guardrail_rules: JSON.stringify(t.guardrail_rules ?? {}, null, 2),
      });
      setDocs(await adminApi.documents(id));
      setSessions((await adminApi.sessions(id)).sessions ?? []);
    } catch (e: any) {
      setError(e.message ?? "Failed to load tenant");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    let guardrail_rules: any;
    try {
      guardrail_rules = JSON.parse(form.guardrail_rules || "{}");
    } catch {
      setError("guardrail_rules must be valid JSON");
      setSaving(false);
      return;
    }
    try {
      const updated = await adminApi.updateTenant(id, {
        rate_limit_plan: form.plan,
        industry: form.industry,
        system_prompt: form.system_prompt || undefined,
        guardrail_rules,
      });
      setTenant(updated);
      setError("Saved");
    } catch (e: any) {
      setError(e.message ?? "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive() {
    if (!tenant) return;
    try {
      await adminApi.updateTenant(id, { is_active: !tenant.is_active });
      load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function regenerate() {
    try {
      const res = await adminApi.regenerateKey(id);
      setRevealedKey(res.api_key);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove() {
    if (!window.confirm(`Permanently delete "${tenant?.name}"? This is irreversible.`)) return;
    try {
      await adminApi.deleteTenant(id);
      router.push("/admin/tenants");
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }
  if (!tenant) {
    return <p className="text-sm text-red-600">{error || "Tenant not found"}</p>;
  }

  return (
    <div className="max-w-2xl grid gap-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{tenant.name}</h1>
          <div className="text-sm text-muted-foreground">
            {tenant.slug} · {tenant.industry || "no industry"}
            {tenant.is_active ? <Badge variant="success" className="ml-2">active</Badge> : <Badge variant="warning" className="ml-2">disabled</Badge>}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {tenant.document_count} docs · {tenant.session_count} sessions · {tenant.message_count} messages
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={regenerate}>
            Regenerate key
          </Button>
          <Button variant="outline" size="sm" onClick={toggleActive}>
            {tenant.is_active ? "Disable" : "Enable"}
          </Button>
          <Button variant="destructive" size="sm" onClick={remove}>
            Delete
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <form onSubmit={save} className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>Plan, industry and system prompt.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="plan">Rate-limit plan</Label>
              <select id="plan" value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })} className="h-9 rounded-md border bg-background px-3 text-sm">
                <option>free</option><option>pro</option><option>enterprise</option>
              </select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="industry">Industry</Label>
              <Input id="industry" value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="system_prompt">System prompt</Label>
              <Textarea rows={3} value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="guardrail_rules">guardrail_rules (JSON)</Label>
              <Textarea rows={5} className="font-mono text-xs" value={form.guardrail_rules} onChange={(e) => setForm({ ...form, guardrail_rules: e.target.value })} />
            </div>
            <div>
              <Button type="submit" disabled={saving}>{saving ? <Spinner /> : "Save changes"}</Button>
            </div>
          </CardContent>
        </Card>
      </form>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>Activity</CardTitle>
          <div className="flex gap-1">
            <button onClick={() => setTab("docs")} className={cn("rounded px-2 py-1 text-sm", tab === "docs" && "bg-accent")}>Documents</button>
            <button onClick={() => setTab("sessions")} className={cn("rounded px-2 py-1 text-sm", tab === "sessions" && "bg-accent")}>Sessions</button>
          </div>
        </CardHeader>
        <CardContent>
          {tab === "docs" ? (
            docs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No documents.</p>
            ) : (
              <ul className="divide-y text-sm">
                {docs.map((d) => (
                  <li key={d.id} className="flex items-center justify-between py-2">
                    <span className="truncate">{d.filename}</span>
                    <Badge variant={d.status === "indexed" ? "success" : d.status === "failed" ? "destructive" : "warning"}>{d.status}</Badge>
                  </li>
                ))}
              </ul>
            )
          ) : (
            <>
              {sessions.length === 0 && <p className="text-sm text-muted-foreground">No sessions.</p>}
              <ul className="divide-y text-sm">
                {(sessions as any[]).map((s) => (
                  <li key={s.id} className="py-2">
                    <div className="font-medium truncate">{s.title || "Untitled"}</div>
                    <div className="text-xs text-muted-foreground">{s.message_count} messages</div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>

      <KeyReveal title="New tenant API key" value={revealedKey} onClose={() => setRevealedKey("")} />
    </div>
  );
}