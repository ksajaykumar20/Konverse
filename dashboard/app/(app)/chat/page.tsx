"use client";

import { useRef, useState } from "react";
import { Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  confidence?: number;
};

export default function ChatPage() {
  const { tenant } = useTenant();
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const sessionRef = useRef<string | undefined>(undefined);
  const [live, setLive] = useState("");

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || !tenant || busy) return;
    setInput("");
    setNotice(null);
    setTurns((t) => [...t, { role: "user", content: text }]);
    setBusy(true);
    setLive("");

    let acc = "";
    let wasAnswered = false;
    let guardrail = false;
    try {
      for await (const ev of chatStream(`/api/b/chat/${tenant.id}`, {
        message: text,
        session_id: sessionRef.current,
      })) {
        if (ev.type === "session") sessionRef.current = ev.session_id;
        else if (ev.type === "guardrail") guardrail = true;
        else if (ev.type === "token") {
          acc += ev.text;
          setLive(acc);
        } else if (ev.type === "done") {
          acc = ev.text;
          wasAnswered = ev.was_answered;
          setLive(acc);
        }
      }
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Chat failed");
    }
    setLive("");
    setBusy(false);
    setTurns((t) => [
      ...t,
      { role: "assistant", content: acc, wasAnswered, guardrail },
    ]);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Chat playground</h1>
        <p className="text-sm text-muted-foreground">
          Grounded, streaming answers from this tenant&apos;s documents.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4">
          <div className="min-h-[320px] space-y-3 overflow-y-auto rounded-md border p-3">
            {turns.map((t, i) => (
              <div key={i} className={cn("flex", t.role === "user" ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
                    t.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  )}
                >
                  {t.content}
                  {t.role === "assistant" && (
                    <div className="mt-1.5 flex gap-2">
                      {t.guardrail && <Badge variant="destructive">guardrail</Badge>}
                      {t.guardrail || (
                        <>
                          {!t.wasAnswered && <Badge variant="warning">unanswered</Badge>}
                          {t.wasAnswered && <Badge variant="success">answered</Badge>}
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {live && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm whitespace-pre-wrap">
                  {live}
                  <Spinner className="ml-1 inline h-3 w-3" />
                </div>
              </div>
            )}
            {turns.length === 0 && !live && (
              <p className="text-sm text-muted-foreground">
                Ask a question grounded in uploaded documents.
              </p>
            )}
          </div>

          {notice && <p className="text-sm text-destructive">{notice}</p>}

          <form onSubmit={send} className="flex items-end gap-2">
            <Textarea
              className="flex-1 resize-none"
              rows={2}
              placeholder="Type a message…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(e as never);
                }
              }}
              disabled={busy}
            />
            <Button type="submit" disabled={busy || !input.trim()}>
              {busy ? <Spinner /> : <Send className="h-4 w-4" />}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}