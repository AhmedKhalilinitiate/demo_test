import { serve } from "https://deno.land/std@0.224.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405, headers: corsHeaders });

  try {
    const auth = req.headers.get("Authorization") || "";
    if (!auth.startsWith("Bearer ")) {
      return new Response(JSON.stringify({ error: "Missing bearer token" }), { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const { tracker_id } = await req.json();
    if (!tracker_id || typeof tracker_id !== "string") {
      return new Response(JSON.stringify({ error: "tracker_id is required" }), { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const githubToken = Deno.env.get("GITHUB_WORKFLOW_TOKEN");
    const githubRepo = Deno.env.get("GITHUB_REPO") || "AhmedKhalilinitiate/demo_test";
    if (!githubToken) throw new Error("GITHUB_WORKFLOW_TOKEN is not configured");

    const r = await fetch(`https://api.github.com/repos/${githubRepo}/actions/workflows/price-check.yml/dispatches`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${githubToken}`,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs: { tracker_id } }),
    });

    if (!r.ok) {
      const text = await r.text();
      return new Response(JSON.stringify({ error: `GitHub dispatch failed: ${r.status}`, detail: text.slice(0, 500) }), { status: 502, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    return new Response(JSON.stringify({ ok: true, tracker_id, status: "crawl_queued" }), { status: 202, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e?.message || e) }), { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
