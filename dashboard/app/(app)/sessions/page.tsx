"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronRight, Clock3, MessageSquareText, RefreshCw, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useTenant } from "@/lib/tenant-context";
import { cn } from "@/lib/utils";

type Session = { id: string; title?: string | null; created_at?: string; updated_at?: string; message_count: number };
type Msg = { role: string; content: string; was_answered?: boolean | null; confidence?: number | null; guardrail_category?: string | null };

function displayDate(value?: string) {
  if (!value) return "Recently active";
  const date = new Date(value);
  const elapsed = Date.now() - date.getTime();
  if (elapsed < 86_400_000) return "Today";
  if (elapsed < 172_800_000) return "Yesterday";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

export default function SessionsPage() {
  const { tenant } = useTenant();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState<Session | null>(null);
  const [transcript, setTranscript] = useState<Msg[] | null>(null);
  const [transcriptBusy, setTranscriptBusy] = useState(false);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/b/chat/${tenant.id}/sessions`);
      if (res.ok) setSessions((await res.json()).sessions ?? []);
    } finally { setLoading(false); }
  }, [tenant]);

  useEffect(() => { if (tenant) load(); }, [tenant, load]);

  async function openSession(session: Session) {
    setActive(session);
    setTranscriptBusy(true);
    setTranscript(null);
    try {
      const res = await fetch(`/api/b/chat/${tenant!.id}/history/${session.id}`);
      if (res.ok) setTranscript((await res.json()).messages ?? []);
    } finally { setTranscriptBusy(false); }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Conversation history</p>
          <h1 className="text-3xl font-semibold tracking-tight">Sessions</h1>
          <p className="mt-2 text-sm text-muted-foreground">Review the conversations your workspace has had with the assistant.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load}><RefreshCw className="mr-1.5 h-4 w-4" /> Refresh</Button>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.85fr)]">
        <Card className="overflow-hidden border-border/80 bg-white/80 shadow-sm">
          <div className="border-b bg-muted/30 px-5 py-4"><h2 className="font-semibold">Recent sessions</h2><p className="text-sm text-muted-foreground">{sessions.length} saved conversation{sessions.length === 1 ? "" : "s"}</p></div>
          <CardContent className="p-0">
            {loading ? <div className="flex justify-center py-14"><Spinner /></div> : sessions.length === 0 ? <EmptySessions /> : <div className="divide-y">{sessions.map((session) => <button key={session.id} onClick={() => openSession(session)} className={cn("flex w-full items-center gap-4 px-5 py-4 text-left transition hover:bg-muted/55", active?.id === session.id && "bg-primary/5")}>{<span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><MessageSquareText className="h-4 w-4" /></span>}<span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{session.title || "Untitled conversation"}</span><span className="mt-1 flex items-center gap-2 text-xs text-muted-foreground"><Clock3 className="h-3 w-3" /> {displayDate(session.updated_at)} <span>·</span> {session.message_count} message{session.message_count === 1 ? "" : "s"}</span></span><ChevronRight className="h-4 w-4 text-muted-foreground" /></button>)}</div>}
          </CardContent>
        </Card>

        <Card className="min-h-[420px] overflow-hidden border-border/80 bg-white/80 shadow-sm">
          {active ? <Transcript session={active} transcript={transcript} busy={transcriptBusy} onClose={() => { setActive(null); setTranscript(null); }} /> : <div className="grid h-full min-h-[420px] place-items-center p-8 text-center"><div><span className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-xl bg-primary/10 text-primary"><Bot className="h-5 w-5" /></span><h2 className="font-semibold">Select a session</h2><p className="mt-2 max-w-xs text-sm leading-6 text-muted-foreground">Choose a conversation to view its full transcript and answer status.</p></div></div>}
        </Card>
      </div>
    </div>
  );
}

function EmptySessions() { return <div className="px-5 py-14 text-center"><MessageSquareText className="mx-auto mb-3 h-7 w-7 text-muted-foreground/60" /><p className="font-medium">No conversations yet</p><p className="mt-1 text-sm text-muted-foreground">Your chat history will appear here once you start asking questions.</p></div>; }

function Transcript({ session, transcript, busy, onClose }: { session: Session; transcript: Msg[] | null; busy: boolean; onClose: () => void }) {
  return <div className="flex h-full min-h-[420px] flex-col"><div className="flex items-start justify-between border-b bg-muted/30 px-5 py-4"><div className="min-w-0"><h2 className="truncate font-semibold">{session.title || "Untitled conversation"}</h2><p className="mt-1 text-sm text-muted-foreground">{session.message_count} messages · {displayDate(session.updated_at)}</p></div><Button variant="ghost" size="icon" onClick={onClose} aria-label="Close transcript"><X className="h-4 w-4" /></Button></div><div className="flex-1 space-y-4 overflow-y-auto p-5">{busy ? <div className="flex justify-center py-12"><Spinner /></div> : transcript?.map((message, index) => <div key={index} className={cn("flex gap-2", message.role === "user" ? "justify-end" : "justify-start")}><div className={cn("max-w-[92%] rounded-xl px-3 py-2.5 text-sm leading-6 whitespace-pre-wrap", message.role === "user" ? "bg-primary text-primary-foreground" : "border bg-muted/45")}>{message.content}{message.role === "assistant" && <div className="mt-2 flex items-center gap-2 border-t border-border/60 pt-2">{message.guardrail_category ? <Badge variant="destructive">guardrail</Badge> : <Badge variant={message.was_answered ? "success" : "warning"}>{message.was_answered ? "grounded answer" : "limited answer"}</Badge>}{typeof message.confidence === "number" && <span className="text-xs text-muted-foreground">Confidence {message.confidence.toFixed(2)}</span>}</div>}</div></div>)}</div></div>;
}
