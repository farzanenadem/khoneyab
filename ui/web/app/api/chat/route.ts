// The LLM agent can take longer than the rewrite proxy's timeout, so /api/chat is
// forwarded by this route handler instead (route handlers take precedence over rewrites).
const API_URL = (process.env.JOB_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const dynamic = "force-dynamic";
export const maxDuration = 180;

export async function POST(request: Request) {
  try {
    const res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      signal: AbortSignal.timeout(180_000),
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return Response.json({ detail: `chat backend unreachable: ${detail}` }, { status: 502 });
  }
}
