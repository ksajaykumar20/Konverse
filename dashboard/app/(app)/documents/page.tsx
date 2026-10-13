"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Clock3, FileText, FileUp, RefreshCw, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTenant } from "@/lib/tenant-context";
import { cn } from "@/lib/utils";

type Doc = {
  id: string;
  filename: string;
  status: string;
  chunk_count?: number;
  error_message?: string | null;
  created_at?: string;
};

function StatusBadge({ status }: { status: string }) {
  const variant = status === "indexed" ? "success" : status === "failed" ? "destructive" : "warning";
  return <Badge variant={variant as never}>{status}</Badge>;
}

function formatDate(value?: string) {
  if (!value) return "Recently added";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

export default function DocumentsPage() {
  const { tenant } = useTenant();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!tenant) return;
    try {
      const res = await fetch(`/api/b/documents/${tenant.id}`);
      if (res.ok) setDocs(await res.json());
    } catch {
      // Keep the last known document list if a refresh fails.
    }
  }, [tenant]);

  useEffect(() => {
    if (tenant) load();
  }, [tenant, load]);

  useEffect(() => {
    if (!tenant || !docs.some((d) => d.status === "processing")) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [docs, tenant, load]);

  function selectFile(nextFile: File | null) {
    setFile(nextFile);
    setError(null);
  }

  async function upload() {
    if (!tenant || !file) return;
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`/api/b/ingest/${tenant.id}`, { method: "POST", body });
      if (res.ok) {
        setFile(null);
        if (fileInput.current) fileInput.current.value = "";
        await load();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? "Upload failed");
      }
    } catch {
      setError("Upload failed");
    } finally {
      setUploading(false);
    }
  }

  const indexed = docs.filter((d) => d.status === "indexed").length;
  const processing = docs.filter((d) => d.status === "processing").length;
  const failed = docs.filter((d) => d.status === "failed").length;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Knowledge base</p>
          <h1 className="text-3xl font-semibold tracking-tight">Documents</h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">Bring in the material your assistant should use to answer with confidence.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="self-start sm:self-auto">
          <RefreshCw className="mr-1.5 h-4 w-4" /> Refresh
        </Button>
      </header>

      <section className="grid gap-3 sm:grid-cols-3">
        <Stat label="Ready to use" value={indexed} icon={CheckCircle2} tone="text-emerald-600 bg-emerald-50" />
        <Stat label="Processing" value={processing} icon={Clock3} tone="text-amber-600 bg-amber-50" />
        <Stat label="Needs attention" value={failed} icon={AlertCircle} tone="text-rose-600 bg-rose-50" />
      </section>

      <section className="rounded-2xl border border-dashed border-primary/35 bg-white/75 p-4 shadow-sm sm:p-6">
        <input ref={fileInput} type="file" className="sr-only" onChange={(e) => selectFile(e.target.files?.[0] ?? null)} />
        <div
          role="button"
          tabIndex={0}
          onClick={() => fileInput.current?.click()}
          onKeyDown={(e) => e.key === "Enter" && fileInput.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); selectFile(e.dataTransfer.files?.[0] ?? null); }}
          className={cn(
            "flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-xl border border-transparent px-5 text-center transition-colors",
            dragging ? "border-primary bg-primary/10" : "hover:bg-muted/60"
          )}
        >
          <span className="mb-3 grid h-11 w-11 place-items-center rounded-xl bg-primary/10 text-primary"><FileUp className="h-5 w-5" /></span>
          <p className="font-medium">Drop a document here, or browse</p>
          <p className="mt-1 text-sm text-muted-foreground">Files are securely extracted, chunked, and indexed in the background.</p>
          {file && <p className="mt-4 rounded-full bg-muted px-3 py-1 text-sm font-medium text-foreground">Selected: {file.name}</p>}
        </div>
        {file && (
          <div className="mt-4 flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-sm text-muted-foreground">Ready to add {file.name}</span>
            <Button onClick={upload} disabled={uploading}>
              {uploading ? <Spinner /> : <Upload className="h-4 w-4" />}
              {uploading ? "Uploading..." : "Add to knowledge base"}
            </Button>
          </div>
        )}
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </section>

      <Card className="overflow-hidden border-border/80 shadow-sm">
        <div className="flex items-center justify-between border-b bg-white/70 px-5 py-4">
          <div>
            <h2 className="font-semibold">Your sources</h2>
            <p className="text-sm text-muted-foreground">{docs.length} document{docs.length === 1 ? "" : "s"} in this workspace</p>
          </div>
        </div>
        <CardContent className="p-0">
          <Table>
            <TableHeader><TableRow><TableHead className="pl-5">Document</TableHead><TableHead>Status</TableHead><TableHead>Chunks</TableHead><TableHead className="hidden md:table-cell">Added</TableHead><TableHead className="pr-5">Details</TableHead></TableRow></TableHeader>
            <TableBody>
              {docs.length === 0 && (
                <TableRow><TableCell colSpan={5} className="px-5 py-14 text-center"><FileText className="mx-auto mb-3 h-7 w-7 text-muted-foreground/60" /><p className="font-medium">Your knowledge base is empty</p><p className="mt-1 text-sm text-muted-foreground">Upload your first source to start a conversation.</p></TableCell></TableRow>
              )}
              {docs.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="pl-5 font-medium">{doc.filename}</TableCell>
                  <TableCell><StatusBadge status={doc.status} /></TableCell>
                  <TableCell>{doc.chunk_count ?? "-"}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{formatDate(doc.created_at)}</TableCell>
                  <TableCell className="max-w-xs truncate pr-5 text-muted-foreground">{doc.error_message ?? "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value, icon: Icon, tone }: { label: string; value: number; icon: typeof FileText; tone: string }) {
  return <Card className="border-border/70 bg-white/75 shadow-sm"><CardContent className="flex items-center gap-3 p-4"><span className={cn("grid h-9 w-9 place-items-center rounded-lg", tone)}><Icon className="h-4 w-4" /></span><div><p className="text-2xl font-semibold tracking-tight">{value}</p><p className="text-xs text-muted-foreground">{label}</p></div></CardContent></Card>;
}
