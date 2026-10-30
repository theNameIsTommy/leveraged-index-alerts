import commands from "../src/leveraged_alerts/commands.json" with { type: "json" };

const accepted = new Set(commands);

export function isRerun(text) {
  return typeof text === "string" && accepted.has(text.trim().toLowerCase().replace(/\s+/g, " ").replace(/^\//, ""));
}

// Inject fetch for deterministic boundary tests; production uses the Workers Fetch API.
export async function handle(request, env, fetcher = fetch) {
  const configured = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "WEBHOOK_SECRET", "GITHUB_TOKEN"].every(key => env[key]);
  const path = new URL(request.url).pathname;
  if (request.method === "GET" && path === "/health") {
    return Response.json({ ready: configured }, { status: configured ? 200 : 503 });
  }
  if (request.method !== "POST" || path !== "/telegram") return new Response("Not found", { status: 404 });
  if (!configured) return new Response("Not configured", { status: 503 });
  if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
    return new Response("Unauthorized", { status: 401 });
  }

  let update;
  try {
    const body = await request.text();
    if (body.length > 65536) return new Response("Too large", { status: 413 });
    update = JSON.parse(body);
  } catch {
    return new Response("Invalid update", { status: 400 });
  }
  if (!Number.isSafeInteger(update?.update_id) || update.update_id < 0) {
    return new Response("Invalid update ID", { status: 400 });
  }
  const message = update.message;
  if (!message || String(message.chat?.id) !== env.TELEGRAM_CHAT_ID || message.from?.is_bot || !isRerun(message.text)) {
    return new Response("Ignored");
  }

  try {
    const dispatch = await fetcher(
      "https://api.github.com/repos/theNameIsTommy/leveraged-index-alerts/actions/workflows/telegram-webhook.yml/dispatches",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "User-Agent": "leveraged-index-alerts-webhook",
          "X-GitHub-Api-Version": "2026-03-10",
        },
        body: JSON.stringify({ ref: "main", inputs: { update_id: String(update.update_id) } }),
        signal: AbortSignal.timeout(10000),
      },
    );
    if (!dispatch.ok) throw new Error("dispatch");
    const acknowledgment = await fetcher(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: env.TELEGRAM_CHAT_ID,
        text: "Rerun received and queued. I will send the latest completed daily-price summary when the calculation finishes.",
        disable_web_page_preview: true,
      }),
      signal: AbortSignal.timeout(10000),
    });
    if (!acknowledgment.ok || !(await acknowledgment.json()).ok) throw new Error("acknowledgment");
    return new Response("Accepted");
  } catch {
    // Non-2xx asks Telegram to retry; the GitHub handler deduplicates update IDs.
    console.error("Webhook delivery failed; Telegram should retry.");
    return new Response("Retry later", { status: 503 });
  }
}

export default { fetch(request, env) { return handle(request, env); } };
