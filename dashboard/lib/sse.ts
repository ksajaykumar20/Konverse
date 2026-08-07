/** Client-side parser for the backend's SSE chat stream (via the proxy). */

export type ChatEvent =
  | { type: "session"; session_id: string }
  | { type: "token"; text: string }
  | { type: "guardrail"; category?: string | null }
  | { type: "done"; text: string; was_answered: boolean };

/** POST `body` to `url` and yield each `data:` event as it arrives. */
export async function* chatStream(
  url: string,
  body: { message: string; session_id?: string }
): AsyncGenerator<ChatEvent> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(`Chat failed (${res.status}): ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (line) {
        yield JSON.parse(line.slice(5).trim()) as ChatEvent;
      }
    }
  }
}