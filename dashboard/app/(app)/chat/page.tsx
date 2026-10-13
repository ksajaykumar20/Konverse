"use client";

import { useRef, useState } from "react";
import { ArrowUp, Bot, FileText, RotateCcw, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useTenant } from "@/lib/tenant-context";
import { chatStream } from "@/lib/sse";
import { cn } from "@/lib/utils";

type Turn = {
  role: "user" | "assistant";
  content: string;
  wasAnswered?: boolean;
  guardrail?: boolean;
};

const SUGGESTIONS = ["What are the main themes in these documents?", "Give me a concise summary of the uploaded material.", "What should I know before getting started?"];

export default function ChatPage() {
  const { tenant } = useTenant();
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [live, setLive] = useState("");
  const sessionRef = useRef<string | undefined>(undefined);

  async function send(event?: React.FormEvent, suggestedText?: string) {
    event?.preventDefault();
    const text = (suggestedText ?? input).trim();
    if (!text || !tenant || busy) return;
    setInput("");
    setNotice(null);
    setTurns((current) => [...current, { role: "user", content: text }]);
    setBusy(true);
    setLive("");

    let answer = "";
    let wasAnswered = false;
    let guardrail = false;
    try {
      for await (const event of chatStream(`/api/b/chat/${tenant.id}`, { message: text, session_id: sessionRef.current })) {
        if (event.type === "session") sessionRef.current = event.session_id;
        else if (event.type === "guardrail") guardrail = true;
        else if (event.type === "token") {
          answer += event.text;
          setLive(answer);
        } else if (event.type === "done") {
          answer = event.text;
          wasAnswered = event.was_answered;
          setLive(answer);
        }
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Chat failed");
    } finally {
      setLive("");
      setBusy(false);
    }
    if (answer) setTurns((current) => [...current, { role: "assistant", content: answer, wasAnswered, guardrail }]);
  }

  function startFresh() {
    sessionRef.current = undefined;
    setTurns([]);
    setLive("");
    setNotice(null);
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-5xl flex-col">
      <header className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Grounded assistant</p>
          <h1 className="text-3xl font-semibold tracking-tight">Ask your knowledge base</h1>
          <p className="mt-2 text-sm text-muted-foreground">Every answer is based on this workspace&apos;s uploaded documents.</p>
        </div>
        {turns.length > 0 && <Button variant="outline" size="sm" onClick={startFresh}><RotateCcw className="mr-1.5 h-4 w-4" /> New conversation</Button>}
      </header>

      <div className="flex flex-1 flex-col overflow-hidden rounded-2xl border border-border/80 bg-white/80 shadow-sm backdrop-blur">
        <div className="flex items-center gap-2 border-b bg-muted/35 px-5 py-3 text-sm">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-primary/10 text-primary"><Bot className="h-4 w-4" /></span>
          <span className="font-medium">Konverse assistant</span>
          <span className="text-muted-foreground">Ready to search your sources</span>
        </div>

        <div className="flex min-h-[360px] flex-1 flex-col gap-5 overflow-y-auto p-4 sm:p-6">
          {turns.length === 0 && !live ? (
            <div className="m-auto max-w-xl text-center">
              <span className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-primary/10 text-primary"><Sparkles className="h-5 w-5" /></span>
              <h2 className="text-xl font-semibold tracking-tight">What would you like to know?</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">Try a question about the documents you&apos;ve added, or use one of these prompts to begin.</p>
              <div className="mt-5 grid gap-2 text-left sm:grid-cols-3">
                {SUGGESTIONS.map((suggestion) => <button key={suggestion} onClick={() => send(undefined, suggestion)} className="rounded-xl border border-border/80 bg-background p-3 text-left text-sm text-muted-foreground transition hover:border-primary/40 hover:bg-primary/5 hover:text-foreground">{suggestion}</button>)}
              </div>
            </div>
          ) : (
            <>
              {turns.map((turn, index) => <Message key={index} turn={turn} />)}
              {live && <Message turn={{ role: "assistant", content: live }} live />}
            </>
          )}
        </div>

        <div className="border-t bg-background/80 p-3 sm:p-4">
          {notice && <p className="mb-2 text-sm text-destructive">{notice}</p>}
          <form onSubmit={send} className="rounded-xl border bg-white p-2 shadow-sm focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/10">
            <Textarea className="min-h-14 resize-none border-0 bg-transparent px-2 py-2 shadow-none focus-visible:ring-0" rows={2} placeholder="Ask a question about your documents..." value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) send(event); }} disabled={busy} />
            <div className="flex items-center justify-between px-1 pt-1">
              <span className="text-xs text-muted-foreground">Enter to send · Shift + Enter for a new line</span>
              <Button type="submit" size="icon" disabled={busy || !input.trim()} aria-label="Send message">{busy ? <Spinner /> : <ArrowUp className="h-4 w-4" />}</Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function Message({ turn, live = false }: { turn: Turn; live?: boolean }) {
  const isUser = turn.role === "user";
  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><Bot className="h-4 w-4" /></span>}
      <div className={cn("max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 whitespace-pre-wrap", isUser ? "rounded-tr-md bg-primary text-primary-foreground" : "rounded-tl-md border bg-muted/45")}> 
        {turn.content}
        {live && <Spinner className="ml-2 inline h-3 w-3" />}
        {!live && !isUser && <div className="mt-2 flex items-center gap-2 border-t border-border/60 pt-2 text-xs">{turn.guardrail ? <Badge variant="destructive">guardrail</Badge> : <><Badge variant={turn.wasAnswered ? "success" : "warning"}>{turn.wasAnswered ? "grounded answer" : "limited answer"}</Badge><span className="text-muted-foreground"><FileText className="mr-1 inline h-3 w-3" />Based on workspace sources</span></>}</div>}
      </div>
    </div>
  );
}
