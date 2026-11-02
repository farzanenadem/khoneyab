"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ListingCard } from "@/components/HomeListings";
import Markdown from "@/components/Markdown";
import { HomeChatResponse, homeChat } from "@/lib/homes";
import Icon from "@/components/Icon";

const EXAMPLES = [
  "آپارتمان دو خواب حدود ۸۰ متر در تهران تا ۸ میلیارد با پارکینگ",
  "خانه نوساز در کرج زیر ۵ میلیارد",
  "حداقل ۱۰۰ متر در تهران، سه خواب",
];

type Turn = { role: "user" | "assistant"; text: string; data?: HomeChatResponse };

export default function HomeChat({ onPickPrice }: { onPickPrice: (p: number) => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<Record<string, unknown> | null>(null);
  const [threadId, setThreadId] = useState(() => `home-${Date.now()}`);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, loading]);

  const send = async (text: string) => {
    const msg = text.trim();
    if (msg.length < 2 || loading) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const data = await homeChat(msg, threadId, filters);
      setFilters(data.filters);
      setTurns((t) => [...t, { role: "assistant", text: data.reply, data }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "assistant", text: `خطا در ارتباط با دستیار: ${e instanceof Error ? e.message : e}` }]);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setTurns([]);
    setFilters(null);
    setThreadId(`home-${Date.now()}`);
  };

  return (
    <section className="card chat h-chat">
      <div className="chat-head">
        <div>
          <div className="chat-kicker">جست‌وجوی گفت‌وگویی</div>
          <div className="chat-title"><span className="chat-title-icon"><Icon name="chat" size={18} /></span><strong>با خونه‌یاب حرف بزن</strong><span className="ai-pill"><span className="live-dot" /> آنلاین</span></div>
          <p className="muted small">خانه‌ای که می‌خواهی را با زبان خودت توصیف کن؛ جزئیات را در ادامه اصلاح می‌کنیم.</p>
        </div>
        {turns.length > 0 && (
          <button type="button" className="link-btn" onClick={reset}>
            <Icon name="refresh" size={15} /> گفتگوی جدید
          </button>
        )}
      </div>

      <div className="chat-log" ref={logRef} aria-live="polite">
        {turns.length === 0 && (
          <>
            <div className="samples-intro"><span>از اینجا شروع کن</span><small>یک نمونه را انتخاب کن یا خودت بنویس</small></div>
            <div className="samples">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" className="sample" onClick={() => send(ex)}>
                  <span className="sample-icon"><Icon name={ex.includes("کرج") ? "pin" : ex.includes("وام") ? "calculator" : "search"} size={16} /></span>
                  <span className="sample-label">{ex}</span>
                  <Icon name="arrow" size={14} className="sample-arrow" />
                </button>
              ))}
            </div>
          </>
        )}
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "bubble bubble-user" : "bubble bubble-assistant"}>
            {t.role === "assistant" ? <Markdown text={t.text} /> : t.text}
            {t.data && t.data.understood.length > 0 && (
              <div className="chat-sources">
                {t.data.understood.map((u) => (
                  <span key={u} className="chip">{u}</span>
                ))}
                {t.data.relaxed.map((u) => (
                  <span key={u} className="tag tag-red">آسان‌تر: {u}</span>
                ))}
              </div>
            )}
            {t.data && t.data.results.length > 0 && (
              <div className="h-grid h-chat-grid">
                {t.data.results.map((r, n) => (
                  <div key={r.id} className="h-chat-item">
                    <span className="h-chat-num">{(n + 1).toLocaleString("fa-IR")}</span>
                    <ListingCard r={r} onPickPrice={onPickPrice} />
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="bubble bubble-assistant h-typing"><span className="loading-dots"><i /><i /><i /></span> در حال جستجو در آگهی‌ها…</div>}
      </div>

      <div className="composer-shell">
        <div className="composer-label"><span><Icon name="sparkles" size={14} /> جست‌وجوی جدید</span><small>Enter برای ارسال · Shift + Enter برای خط بعد</small></div>
        <form
          className="chat-input"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            send(input);
          }}
        >
          <textarea
            rows={1}
            value={input}
            placeholder="مثلاً: آپارتمان دوخوابه در تهران تا ۷ میلیارد با پارکینگ…"
            aria-label="پیام به دستیار"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
          />
          <button className="btn btn-primary" type="submit" disabled={loading || input.trim().length < 2}>
            جست‌وجو <Icon name="arrow" size={15} />
          </button>
        </form>
        <p className="chat-note"><Icon name="shield" size={13} /> نتیجه‌ها از آگهی‌های واقعی می‌آیند؛ اگر چیزی در آگهی نباشد، حدس نمی‌زنیم.</p>
      </div>
    </section>
  );
}
