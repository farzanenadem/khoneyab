"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Markdown from "@/components/Markdown";
import { sendChat } from "@/lib/api";

type Message = { role: "user" | "assistant"; content: string; sources?: { title?: string; url?: string }[] };

function newThreadId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : String(Date.now());
}

/** A message sent from outside (the shared search box); `nonce` makes repeats distinct. */
export type ChatSeed = { text: string; nonce: number };

export default function ChatPanel({ seed }: { seed?: ChatSeed | null }) {
  const [threadId, setThreadId] = useState(newThreadId);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length || loading) endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, loading]);

  useEffect(() => {
    if (seed) send(seed.text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.nonce]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    send(input);
  };

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || loading) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const res = await sendChat(text, threadId);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.response, sources: res.sources.map((s) => s.metadata) },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat">
      <div className="chat-head">
        <p className="muted small">
          دستیار شغلی با مدل زبانی (DeepSeek از طریق Metis) فقط بر اساس آگهی‌های واقعی پاسخ می‌دهد. می‌توانید
          ادامه گفتگو را کوتاه بنویسید؛ مثلاً «فقط پاره وقت» یا «در اصفهان چی؟».
        </p>
        <button
          type="button"
          className="link-btn"
          onClick={() => {
            setThreadId(newThreadId());
            setMessages([]);
          }}
        >
          گفتگوی جدید
        </button>
      </div>

      <div className="chat-log">
        {messages.length === 0 && (
          <div className="empty">
            <div className="empty-icon">💬</div>
            خواسته‌تان را در کادر بالا بنویسید؛ دستیار آگهی‌های مناسب را پیدا می‌کند و توضیح می‌دهد. سپس همین‌جا ادامه دهید.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role}`}>
            {m.role === "assistant" ? <Markdown text={m.content} /> : m.content}
            {m.sources && m.sources.length > 0 && (
              <div className="chat-sources">
                <span className="muted small">آگهی‌های بررسی‌شده:</span>
                {m.sources.map((s, j) =>
                  s.url ? (
                    <a key={j} href={s.url} target="_blank" rel="noopener noreferrer" className="tag">
                      {s.title}
                    </a>
                  ) : null,
                )}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="bubble bubble-assistant muted">در حال بررسی آگهی‌ها… (ممکن است تا یک دقیقه طول بکشد)</div>}
        {error && <div className="alert">خطا: {error}</div>}
        <div ref={endRef} />
      </div>

      <form className="chat-input" onSubmit={submit}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={2}
          placeholder="ادامه گفتگو… مثلاً «فقط دورکاری» یا «در اصفهان چی؟»"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) submit(e);
          }}
          aria-label="پیام"
        />
        <button className="btn btn-primary" type="submit" disabled={loading || !input.trim()}>
          ارسال
        </button>
      </form>
    </div>
  );
}
