"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useTenant } from "@/lib/tenant-context";

type Doc = {
  id: string;
  filename: string;
  status: string;
  chunk_count?: number;
  error_message?: string | null;
  created_at?: string;
};

function StatusBadge({ status }: { status: string }) {
  const variant =
    status === "indexed"
      ? "success"
      : status === "failed"
        ? "destructive"
        : "warning";
  return <Badge variant={variant as never}>{status}</Badge>;
}

export default function DocumentsPage() {
  const { tenant } = useTenant();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!tenant) return;
    try {
      const res = await fetch(`/api/b/documents/${tenant.id}`);
      if (res.ok) setDocs(await res.json());
    } catch {
      /* keep last known list */
    }
  }, [tenant]);

  useEffect(() => {
    if (tenant) load();
  }, [tenant, load]);

  // Poll while any document is still processing.
  useEffect(() => {
    if (!tenant) return;
    if (!docs.some((d) => d.status === "processing")) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [docs, tenant, load]);

  async function upload() {
    if (!tenant || !file) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`/api/b/ingest/${tenant.id}`, {
        method: "POST",
        body: fd,
      });
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Documents</h1>
          <p className="text-sm text-muted-foreground">
            Upload files the chatbot is grounded on.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw className="mr-1 h-4 w-4" /> Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload</CardTitle>
          <CardDescription>
            Ingestion is async — a worker extracts, chunks, embeds, and indexes chunks.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <input
            ref={fileInput}
            type="file"
            className="flex-1 text-sm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button onClick={upload} disabled={!file || uploading}>
            {uploading ? <Spinner /> : <Upload className="mr-1 h-4 w-4" />}
            {uploading ? "Uploading…" : "Upload"}
          </Button>
        </CardContent>
        {error && <CardContent className="pt-0"><p className="text-sm text-destructive">{error}</p></CardContent>}
      </Card>

      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Chunks</TableHead>
                <TableHead>Error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground">
                    No documents yet.
                  </TableCell>
                </TableRow>
              )}
              {docs.map((d) => (
                <TableRow key={d.id}>
                  <TableCell>{d.filename}</TableCell>
                  <TableCell><StatusBadge status={d.status} /></TableCell>
                  <TableCell>{d.chunk_count ?? "—"}</TableCell>
                  <TableCell className="max-w-xs truncate text-muted-foreground">
                    {d.error_message ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}