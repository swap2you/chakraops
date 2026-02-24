/**
 * R23.4: Ticker Copilot — read-only Q&A panel on Symbol page.
 * R23.4.1: Error banner for error_code (COPILOT_KEY_MISSING, COPILOT_AUTH_FAILED, etc.) with "How to fix".
 */
import { useState, useCallback } from "react";
import { apiPost, ApiError } from "@/api/client";
import { ENDPOINTS } from "@/data/endpoints";
import { Card, CardHeader, Button } from "@/components/ui";
import { Send, Copy, Loader2, MessageCircle, AlertTriangle } from "lucide-react";

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
  requestId?: string;
}

export interface CopilotAskResponse {
  answer_markdown: string;
  citations: Array<{ tool: string; at: string }>;
  followups: string[];
  used_tools: string[];
  snapshot_used: boolean;
  request_id: string;
}

/** R23.4.1: Error payload when Copilot returns 502/503/500 with error_code. */
export interface CopilotErrorPayload {
  error_code: string;
  message: string;
}

function copilotFixHint(errorCode: string): string {
  if (
    errorCode === "COPILOT_KEY_MISSING" ||
    errorCode === "COPILOT_AUTH_FAILED"
  ) {
    return "Set COPILOT_OPENAI_API_KEY in backend env and restart uvicorn.";
  }
  if (errorCode === "COPILOT_KEY_MALFORMED") {
    return "Key looks malformed (quotes/spaces). Fix .env and restart.";
  }
  if (errorCode === "COPILOT_UPSTREAM_UNAVAILABLE") {
    return "Try again later.";
  }
  return "Check server logs or try again.";
}

const DEFAULT_CHIPS = [
  "Why is this symbol not eligible?",
  "What delta missed the band and by how much?",
  "What are the key support/resistance levels?",
  "What is my position/holdings exposure?",
  "Is data fresh and scheduler healthy?",
];

/** Sanitize markdown for safe display: escape HTML, allow \n and **bold**. */
function safeMarkdownToHtml(md: string): string {
  if (!md) return "";
  const escaped = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
  const withBold = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return withBold.replace(/\n/g, "<br />");
}

/** R23.4.2: Optional system health; if copilot.key_present && !key_format_ok show malformed hint. */
export interface CopilotSystemHealth {
  copilot?: { key_present?: boolean; key_format_ok?: boolean };
}

export function CopilotPanel({
  symbol,
  conversationId,
  systemHealth,
}: {
  symbol: string;
  conversationId: string;
  systemHealth?: CopilotSystemHealth | null;
}) {
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copilotError, setCopilotError] = useState<CopilotErrorPayload | null>(null);

  const copilotStatus = systemHealth?.copilot;
  const showMalformedHint =
    Boolean(copilotStatus?.key_present && copilotStatus?.key_format_ok === false) && !copilotError;

  const sendQuestion = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q) return;
      setError(null);
      setCopilotError(null);
      setMessages((prev) => [...prev, { role: "user", content: q }]);
      setInput("");
      setLoading(true);
      try {
        const res = await apiPost<CopilotAskResponse>(ENDPOINTS.copilotAsk, {
          symbol: symbol || undefined,
          question: q,
          conversation_id: conversationId,
          mode: "symbol",
        });
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: res.answer_markdown, requestId: res.request_id },
        ]);
      } catch (e) {
        const body = e instanceof ApiError ? (e.body as CopilotErrorPayload | undefined) : undefined;
        if (body?.error_code) {
          setCopilotError({ error_code: body.error_code, message: body.message || "Copilot unavailable." });
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: body.message || "Copilot unavailable." },
          ]);
        } else {
          const msg = e instanceof Error ? e.message : String(e);
          setError(msg);
          setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${msg}` }]);
        }
      } finally {
        setLoading(false);
      }
    },
    [symbol, conversationId]
  );

  const handleCopy = useCallback((text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  }, []);

  return (
    <Card className="flex flex-col h-full min-h-[320px]">
      <CardHeader
        title="Copilot"
        description="Ask about this symbol or system (read-only)."
      />
      <div className="flex flex-col flex-1 min-h-0 gap-2">
        {(copilotError || showMalformedHint) && (
          <div
            className="rounded border border-amber-500/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200"
            role="alert"
          >
            <p className="font-medium flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              Copilot unavailable
            </p>
            {copilotError ? (
              <>
                <p className="mt-1 text-amber-200/90">{copilotError.message}</p>
                <p className="mt-1 text-xs text-amber-300/80">
                  How to fix: {copilotFixHint(copilotError.error_code)}
                </p>
              </>
            ) : showMalformedHint ? (
              <p className="mt-1 text-xs text-amber-300/80">
                Key looks malformed (quotes/spaces). Fix .env and restart uvicorn.
              </p>
            ) : null}
          </div>
        )}
        <div className="flex flex-wrap gap-1.5 mb-2">
          {DEFAULT_CHIPS.map((label) => (
            <button
              key={label}
              type="button"
              onClick={() => sendQuestion(label)}
              disabled={loading}
              className="text-xs px-2 py-1 rounded border border-zinc-600 bg-zinc-800/50 text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto space-y-2 rounded border border-zinc-700 bg-zinc-900/50 p-2 min-h-[120px]">
          {messages.length === 0 && (
            <p className="text-xs text-zinc-500 flex items-center gap-1">
              <MessageCircle className="w-3 h-3" />
              Ask a question or pick a suggestion above.
            </p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`text-sm ${
                m.role === "user"
                  ? "text-right text-zinc-300"
                  : "text-left text-zinc-200"
              }`}
            >
              {m.role === "user" ? (
                <span>{m.content}</span>
              ) : (
                <div className="flex flex-col gap-1">
                  <div
                    className="prose prose-invert prose-sm max-w-none break-words"
                    dangerouslySetInnerHTML={{
                      __html: safeMarkdownToHtml(m.content),
                    }}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="self-start h-6 text-xs text-zinc-500 hover:text-zinc-300"
                    onClick={() => handleCopy(m.content)}
                  >
                    <Copy className="w-3 h-3 mr-1" />
                    Copy answer
                  </Button>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <p className="text-xs text-zinc-500 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              Thinking…
            </p>
          )}
        </div>
        {error && (
          <p className="text-xs text-amber-500" role="alert">
            {error}
          </p>
        )}
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            sendQuestion(input);
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about this symbol…"
            className="flex-1 min-w-0 rounded border border-zinc-600 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-500"
            disabled={loading}
          />
          <Button
            type="submit"
            disabled={loading || !input.trim()}
            className="shrink-0"
          >
            <Send className="w-4 h-4" />
          </Button>
        </form>
      </div>
    </Card>
  );
}
