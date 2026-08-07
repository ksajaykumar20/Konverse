/*!
 * Konverse embeddable chat widget.
 *
 * Vanilla JS, zero dependencies, mounted inside a Shadow DOM so the host
 * page's CSS cannot leak in. Speaks directly to the backend SSE chat
 * endpoint (mirrors the dashboard's conversation contract):
 *
 *     POST /api/chat/{tenantId}   -> text/event-stream
 *        session   {session_id}
 *        guardrail {category}       (refusal — question was barred)
 *        token     {text}           (incremental answer tokens)
 *        done      {text, was_answered}
 *
 * Embed on any tenant page:
 *     <script src="https://<host>/static/widget.js"></script>
 *     <script>
 *       Konverse.init({ tenantId: "…", apiKey: "sk_…", baseUrl: "…", title: "…" });
 *     </script>
 *
 * NOTE: passing the tenant API key on the page is a POC convenience. For
 * production use a low-privilege, origin-scoped widget key or a short-lived
 * token exchange so end users never see the raw key.
 */
(function (global) {
  "use strict";

  var VERSION = "0.2.0";

  var DEFAULTS = {
    title: "Konverse",
    greeting: "Hi, ask about our documentation.",
    placeholder: "Type a question…",
    position: "bottom-right", // "bottom-right" | "bottom-left"
    accentColor: "#2563eb",
    baseUrl: "", // '' = same origin; else the backend origin
  };

  /* Icons as inline SVG (no icon dependency). */
  var ICONS = {
    bubble:
      '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    close:
      '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    send:
      '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
  };

  function configure(config) {
    if (!config || !config.tenantId || !config.apiKey) {
      throw new Error("Konverse.init requires tenantId and apiKey.");
    }
    return _configure(config);
  }

  function _configure(config) {
    var settings = {};
    var key2;
    for (key2 in DEFAULTS)
      if (Object.prototype.hasOwnProperty.call(DEFAULTS, key2))
        settings[key2] = DEFAULTS[key2];
    for (key2 in config)
      if (Object.prototype.hasOwnProperty.call(config, key2))
        settings[key2] = config[key2];

    var existing = document.getElementById("konverse-widget");
    if (existing) existing.remove();

    var host = document.createElement("div");
    host.id = "konverse-widget";
    document.body.appendChild(host);

    var root = host.attachShadow({ mode: "open" });
    root._sessionId = undefined;
    buildWidget(root, settings);
    return { version: VERSION };
  }

  /* ------------------------------- rendering ----------------------------- */

  function buildWidget(root, settings) {
    root.innerHTML = "<style>" + css(settings) + "</style>" + html(settings);

    var bubble = root.querySelector(".kw-toggle");
    var panel = root.querySelector(".kw-panel");
    var close = root.querySelector(".kw-close");
    var title = root.querySelector(".kw-title");
    var input = root.querySelector(".kw-input");
    var form = root.querySelector(".kw-form");

    title.textContent = settings.title;
    input.placeholder = settings.placeholder;
    addMessage(root, "assistant", settings.greeting);

    bubble.addEventListener("click", function () {
      var open = panel.hidden;
      panel.hidden = !open;
      bubble.setAttribute("aria-expanded", String(open));
      if (open) input.focus();
    });
    close.addEventListener("click", function () {
      panel.hidden = true;
      bubble.setAttribute("aria-expanded", "false");
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = input.value.trim();
      if (!text) return;
      input.value = "";
      send(root, settings, text);
    });
  }

  function html(s) {
    return (
      '<button class="kw-toggle" aria-expanded="false" aria-label="Open chat">' +
      ICONS.bubble +
      "</button>" +
      '<div class="kw-panel" hidden>' +
      '<div class="kw-header"><span class="kw-title"></span>' +
      '<button class="kw-close" aria-label="Close">' +
      ICONS.close +
      "</button></div>" +
      '<div class="kw-messages" aria-live="polite"></div>' +
      '<form class="kw-form">' +
      '<textarea class="kw-input" rows="1"></textarea>' +
      '<button class="kw-send" type="submit" aria-label="Send">' +
      ICONS.send +
      "</button></form></div>"
    );
  }

  function css(s) {
    var isLeft = s.position && s.position !== "bottom-right" && String(s.position).indexOf("left") !== -1;
    var h = isLeft ? "left:24px" : "right:24px";
    return [
      ":host{--accent:" + s.accentColor + "}",
      "*{box-sizing:border-box;font-family:system-ui,'Segoe UI',sans-serif}",
      ".kw-toggle{position:fixed;bottom:20px;" + h + ";z-index:2147483000;width:56px;height:56px;",
      "border-radius:50%;border:none;background:var(--accent);color:#fff;cursor:pointer;",
      "display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,.25)}",
      ".kw-toggle:hover{filter:brightness(1.05)}",
      ".kw-panel{position:fixed;bottom:88px;" + h + ";z-index:2147483001;display:flex;flex-direction:column;",
      "width:min(360px,calc(100vw - 32px));height:480px;border-radius:14px;overflow:hidden;",
      "background:#fff;color:#0f172a;box-shadow:0 12px 40px rgba(0,0,0,.22);border:1px solid rgba(0,0,0,.08)}",
      ".kw-panel[hidden]{display:none}",
      ".kw-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;",
      "background:var(--accent);color:#fff;font-weight:600}",
      ".kw-title{margin:0;font-size:15px}",
      ".kw-close{background:none;border:none;color:#fff;cursor:pointer;padding:2px;display:flex}",
      ".kw-messages{flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:8px}",
      ".kw-msg{max-width:82%;padding:8px 12px;border-radius:12px;font-size:14px;line-height:1.45;",
      "white-space:pre-wrap;word-break:break-word}",
      ".kw-msg.user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:4px}",
      ".kw-msg.assistant{align-self:flex-start;background:#f1f5f9;color:#0f172a;border-bottom-left-radius:4px}",
      ".kw-note{font-size:11px;color:#94a3b8;margin-top:2px}",
      ".kw-note.alert{color:#b91c1c}",
      ".kw-form{display:flex;gap:8px;padding:12px;border-top:1px solid #e2e8f0}",
      ".kw-input{flex:1;border:1px solid #cbd5e1;border-radius:10px;padding:8px 10px;resize:none;",
      "font-family:inherit;font-size:14px}",
      ".kw-input:focus{outline:2px solid var(--accent);outline-offset:-1px}",
      ".kw-send{width:38px;border:none;border-radius:10px;background:var(--accent);color:#fff;cursor:pointer;",
      "display:flex;align-items:center;justify-content:center}",
      ".kw-send:disabled{opacity:.5;cursor:default}",
    ].join("");
  }

  /* ------------------------------ messaging ------------------------------ */

  function addMessage(root, role, content) {
    var container = root.querySelector(".kw-messages");
    var el = document.createElement("div");
    el.className = "kw-msg " + role;
    el.textContent = content || "";
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    return el;
  }

  function addNote(root, text, alert) {
    var el = document.createElement("div");
    el.className = "kw-note" + (alert ? " alert" : "");
    el.textContent = text;
    root.querySelector(".kw-messages").appendChild(el);
  }

  function send(root, settings, text) {
    addMessage(root, "user", text);
    var msgEl = addMessage(root, "assistant", "");

    var input = root.querySelector(".kw-input");
    var sendBtn = root.querySelector(".kw-send");
    sendBtn.disabled = true;
    input.disabled = true;

    var sessionBox = { value: root._sessionId };
    stream(root, settings, text, msgEl, sessionBox).finally(function () {
      root._sessionId = sessionBox.value;
      sendBtn.disabled = false;
      input.disabled = false;
      input.focus();
    });
  }

  /** Open the SSE stream for a turn and render tokens incrementally. */
  async function stream(root, settings, text, msgEl, sessionBox) {
    var base = settings.baseUrl.replace(/\/+$/, "");
    var endpoint = base + "/api/chat/" + encodeURIComponent(settings.tenantId);
    var acc = "";

    try {
      var res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": settings.apiKey,
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ message: text, session_id: sessionBox.value }),
      });

      if (!res.ok || !res.body) {
        msgEl.textContent = "Chat failed (HTTP " + res.status + ").";
        return;
      }

      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";

      for (;;) {
        var out = await reader.read();
        if (out.done) break;
        buffer += decoder.decode(out.value, { stream: true });
        var idx = buffer.indexOf("\n\n");
        while (idx >= 0) {
          handleFrame(buffer.slice(0, idx));
          buffer = buffer.slice(idx + 2);
          idx = buffer.indexOf("\n\n");
        }
      }
    } catch (err) {
      msgEl.textContent =
        "Network error: " + (err && err.message ? err.message : err);
    }

    function handleFrame(frame) {
      var data = null;
      var lines = frame.split("\n");
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].indexOf("data:") === 0) {
          try {
            data = JSON.parse(lines[i].slice(5).trim());
          } catch (e) { /* skip malformed */ }
          break;
        }
      }
      if (!data) return;

      if (data.type === "session") {
        sessionBox.value = data.session_id;
      } else if (data.type === "guardrail") {
        addNote(root, "This question is blocked by a guardrail.", true);
      } else if (data.type === "token") {
        acc += data.text;
        msgEl.textContent = acc;
        root.querySelector(".kw-messages").scrollTop = 1e9;
      } else if (data.type === "done") {
        if (data.text) msgEl.textContent = data.text;
        if (!data.was_answered) {
          addNote(root, "No answer found in the documents.");
        }
      }
    }
  }

  global.Konverse = global.Konverse || {};
  global.Konverse.init = configure;
  global.Konverse.version = VERSION;
})(window);