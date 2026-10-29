// Resume analysis (LLM + live crawl of several boards) can exceed the rewrite proxy's
// timeout, so the multipart upload is forwarded by this route handler instead.
const API_URL = (process.env.JOB_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const dynamic = "force-dynamic";
export const maxDuration = 180;

export async function POST(request: Request) {
  try {
    const res = await fetch(`${API_URL}/resume/search`, {
      method: "POST",
      body: await request.formData(),
      signal: AbortSignal.timeout(180_000),
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return Response.json({ detail: `resume backend unreachable: ${detail}` }, { status: 502 });
  }
}
