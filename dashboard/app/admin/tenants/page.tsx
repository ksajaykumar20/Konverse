"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { KeyRound, Pencil, Plus, Trash2 } from "lucide-react";

import { adminApi } from "@/lib/admin-api";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { KeyReveal } from "@/components/key-reveal";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Tenant = {
  id: string;
  name: string;
  slug: string;
  industry: string;
  rate_limit_plan: string;
  is_active: boolean;
  document_count: number;
  session_count: number;
  message_count: number;
  created_at: string;
};

function statusBadge(active: boolean) {
  return active ? <Badge variant="success">active</Badge> : <Badge variant="warning">disabled</Badge>;
}

export default function AdminTenants() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revealedKey, setRevealedKey] = useState<string>("");

  const load = useCallback(async (query?: string) => {
    setLoading(true);
    setError("");
    try {
      const params = query ? `?q=${encodeURIComponent(query)}` : "";
      const data = await adminApi.listTenants(params);
      setTenants(data.tenants ?? []);
    } catch (e: any) {
      setError(e.message ?? "Failed to load tenants");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => load(q), q ? 300 : 0);
    return () => clearTimeout(t);
  }, [q, load]);

  async function toggle(t: Tenant) {
    try {
      await adminApi.updateTenant(t.id, { is_active: !t.is_active });
      load(q);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function regenerate(t: Tenant) {
    try {
      const res = await adminApi.regenerateKey(t.id);
      setRevealedKey(res.api_key);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(t: Tenant) {
    if (!window.confirm(`Permanently delete "${t.name}"? This purges its documents, Qdrant vectors, sessions and messages. This cannot be undone.`)) return;
    try {
      await adminApi.deleteTenant(t.id);
      load(q);
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Tenants</h1>
        <div className="flex gap-2">
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name or slug…"
            className="w-64"
          />
          <Link href="/admin/tenants/new" className={buttonVariants()}>
            Onboard tenant
          </Link>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Docs</TableHead>
                  <TableHead>Messages</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tenants.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                      No tenants yet.
                    </TableCell>
                  </TableRow>
                )}
                {tenants.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>
                      <Link href={`/admin/tenants/${t.id}`} className="font-medium hover:underline">
                        {t.name}
                      </Link>
                      <div className="text-xs text-muted-foreground">{t.slug} · {t.industry}</div>
                    </TableCell>
                    <TableCell className="capitalize">{t.rate_limit_plan}</TableCell>
                    <TableCell>{statusBadge(t.is_active)}</TableCell>
                    <TableCell>{t.document_count}</TableCell>
                    <TableCell>{t.message_count}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Link
                          href={`/admin/tenants/${t.id}`}
                          className={buttonVariants({ variant: "ghost", size: "sm" })}
                          title="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </Link>
                        <Button variant="ghost" size="sm" onClick={() => regenerate(t)} title="Regenerate key">
                          <KeyRound className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggle(t)}
                        >
                          {t.is_active ? "Disable" : "Enable"}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => remove(t)} title="Hard delete" className="text-red-600">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <KeyReveal
        title="New tenant API key"
        value={revealedKey}
        onClose={() => setRevealedKey("")}
      />
    </div>
  );
}