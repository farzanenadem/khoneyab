import { Fragment, ReactNode } from "react";

// Minimal, safe Markdown for agent answers: headings, lists, rules, **bold**, links.
// Text is rendered as React nodes, never as raw HTML.

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|https?:\/\/[^\s)]+)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<strong key={`${key}-${i++}`}>{tok.slice(2, -2)}</strong>);
    else
      out.push(
        <a key={`${key}-${i++}`} href={tok} target="_blank" rel="noopener noreferrer">
          {decodeURI(tok)}
        </a>,
      );
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export default function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = (k: number) => {
    if (list.length) blocks.push(<ul key={`ul-${k}`}>{list}</ul>);
    list = [];
  };
  text.split("\n").forEach((raw, k) => {
    const line = raw.trimEnd();
    const key = `l${k}`;
    if (/^\s*[-*•]\s+/.test(line)) {
      list.push(<li key={key}>{inline(line.replace(/^\s*[-*•]\s+/, ""), key)}</li>);
      return;
    }
    flush(k);
    if (!line.trim()) return;
    if (/^-{3,}$/.test(line.trim())) blocks.push(<hr key={key} />);
    else if (/^#{1,6}\s/.test(line)) {
      const level = line.match(/^#+/)![0].length;
      const content = inline(line.replace(/^#+\s*/, ""), key);
      blocks.push(level <= 2 ? <h3 key={key}>{content}</h3> : <h4 key={key}>{content}</h4>);
    } else blocks.push(<p key={key}>{inline(line, key)}</p>);
  });
  flush(-1);
  return <Fragment>{blocks}</Fragment>;
}
