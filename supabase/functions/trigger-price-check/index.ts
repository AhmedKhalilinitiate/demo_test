import { serve } from "https://deno.land/std@0.224.0/http/server.ts";

const jsonHeaders = { "Content-Type": "application/json" };
const allowedOrigins = new Set([
  "https://ahmedkhalilinitiate.github.io",
]);

function cors(req: Request) {
  const origin = req.headers.get("Origin") || "";
  const allowOrigin = allowedOrigins.has(origin) ? origin : "https://ahmedkhalilinitiate.github.io";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };
}

function response(req: Request, status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...cors(req), ...jsonHeaders },
  });
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(req) });
  if (req.method !== "POST") return response(req, 405, { error: "Method not allowed" });

  try {
    const origin = req.headers.get("Origin");
    if (origin && !allowedOrigins.has(origin)) {
      return response(req, 403, { error: "Origin not allowed" });
    }

    // This function is intentionally callable from the public GitHub Pages dashboard.
    // Deploy with --no-verify-jwt. We do not compare the public anon key byte-for-byte:
    // Supabase projects may expose different public-key representations across CLI/runtime
    // generations, and the anon key is not a secret. Security here comes from the allowed
    // origin, validating an existing active queued tracker via service role, and keeping the
    // GitHub workflow token server-side.
    if (!req.headers.get("apikey")) {
      return response(req, 401, { error: "Missing Supabase API key" });
    }

    const { tracker_id } = await req.json();
    if (typeof tracker_id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(tracker_id)) {
      return response(req, 400, { error: "A valid tracker_id UUID is required" });
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL") || "";
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
    if (!supabaseUrl || !serviceKey) {
      return response(req, 500, { error: "Supabase function environment is incomplete" });
    }

    const trackerResp = await fetch(
      `${supabaseUrl}/rest/v1/trackers?id=eq.${encodeURIComponent(tracker_id)}&select=id,active,last_status&limit=1`,
      {
        headers: {
          apikey: serviceKey,
          Authorization: `Bearer ${serviceKey}`,
        },
      },
    );
    if (!trackerResp.ok) {
      return response(req, 500, { error: "Could not validate tracker", detail: (await trackerResp.text()).slice(0, 300) });
    }
    const trackers = await trackerResp.json();
    const tracker = trackers?.[0];
    if (!tracker || tracker.active !== true) {
      return response(req, 404, { error: "Tracker not found or inactive" });
    }
    if (!["queued", "discovery_queued", "discovered"].includes(String(tracker.last_status || ""))) {
      return response(req, 200, { ok: true, tracker_id, status: "already_processed" });
    }

    const githubToken = Deno.env.get("GITHUB_WORKFLOW_TOKEN");
    const githubRepo = Deno.env.get("GITHUB_REPO") || "AhmedKhalilinitiate/demo_test";
    if (!githubToken) {
      return response(req, 500, { error: "GITHUB_WORKFLOW_TOKEN is not configured" });
    }

    const gh = await fetch(`https://api.github.com/repos/${githubRepo}/actions/workflows/price-check.yml/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${githubToken}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs: { tracker_id } }),
    });

    if (!gh.ok) {
      const detail = (await gh.text()).slice(0, 500);
      return response(req, 502, {
        error: `GitHub dispatch failed: ${gh.status}`,
        detail,
      });
    }

    return response(req, 202, { ok: true, tracker_id, status: "crawl_queued" });
  } catch (e) {
    return response(req, 500, { error: String(e?.message || e) });
  }
});
