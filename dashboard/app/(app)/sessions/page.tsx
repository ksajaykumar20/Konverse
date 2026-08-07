"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronDown, RefreshCw } from "lucide-react";

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

type Session = {
  id: string;
  title?: string | null;
  created_at?: string;
  updated_at?: string;
  message_count: number;
};

type Msg = {
  role: string;
  content: string;
  was_answered?: boolean | null;
  confidence?: number | null;
  guardrail_category?: string | null;
};

export default function SessionsPage() {
  const { tenant } = useTenant();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<Msg[] | null>(null);
  const [transcriptBusy, setTranscriptBusy] = useState(false);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/b/chat/${tenant.id}/sessions`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => {
    if (tenant) load();
  }, [tenant, load]);

  async function toggle(sessionId: string) {
    if (open === sessionId) {
      setOpen(null);
      setTranscript(null);
      return;
    }
    setOpen(sessionId);
    setTranscriptBusy(true);
    setTranscript(null);
    try {
      const res = await fetch(
        `/api/b/chat/${tenant!.id}/history/${sessionId}`
      );
      if (res.ok) {
        const data = await res.json();
        setTranscript(data.messages ?? []);
      }
    } finally {
      setTranscriptBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Sessions</h1>
          <p className="text-sm text-muted-foreground">
            Recent conversations and their transcripts.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw className="mr-1 h-4 w-4" /> Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead />
                  <TableHead>Title</TableHead>
                  <TableHead>Messages</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-muted-foreground">
                      No sessions yet.
                    </TableCell>
                  </TableRow>
                )}
                {sessions.map((s) => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    open={open === s.id}
                    busy={transcriptBusy && open === s.id}
                    onToggle={() => toggle(s.id)}
                    transcript={transcript}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SessionRow({
  session,
  open,
  busy,
  onToggle,
  transcript,
}: {
  session: Session;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  transcript: Msg[] | null;
}) {
  return (
    <>
      <TableRow onClick={onToggle} className="cursor-pointer">
        <TableCell className="w-8">
          <ChevronDown className={open ? "rotate-180" : ""} />
        </TableCell>
        <TableCell>{session.title || "(untitled)"}</TableCell>
        <TableCell>{session.message_count}</TableCell>
        <TableCell className="text-muted-foreground">
          {session.updated_at ? new Date(session.updated_at).toLocaleString() : "—"}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow>
          <TableCell colSpan={4} className="bg-muted/20">
            {busy ? (
              <div className="flex justify-center py-4">
                <Spinner />
              </div>
            ) : transcript ? (
              <div className="space-y-2">
                {transcript.map((m, i) => (
                  <div key={i} className="rounded-md border bg-background p-2 text-sm">
                    <div className="mb-1 flex items-center gap-2">
                      <span className="text-xs font-medium text-muted-foreground">
                        {m.role}
                      </span>
                      {m.role === "assistant" && (
                        <>
                          {m.guardrail_category && (
                            <Badge variant="destructive">guardrail</Badge>
                          )}
                          {!m.guardrail_category &&
                            (m.was_answered ? (
                              <Badge variant="success">answered</Badge>
                            ) : (
                              <Badge variant="warning">unanswered</Badge>
                            ))}
                          {typeof m.confidence === "number" && (
                            <span className="text-xs text-muted-foreground">
                              conf {m.confidence.toFixed(2)}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                ))}
              </div>
            ) : null}
          </TableCell>
        </TableRow>
      )}
    </>
  );
}