import assert from "node:assert/strict";
import test from "node:test";
import worker, { handle, isRerun } from "./worker.mjs";
import commands from "../src/leveraged_alerts/commands.json" with { type: "json" };

const env = {
  TELEGRAM_BOT_TOKEN: "test-bot-secret", TELEGRAM_CHAT_ID: "123",
  WEBHOOK_SECRET: "test-webhook-secret", GITHUB_TOKEN: "test-github-secret",
};
const update = { update_id: 10, message: { chat: { id: 123 }, from: { is_bot: false }, text: "gO" } };
const request = (body = update, secret = env.WEBHOOK_SECRET) => new Request("https://example.test/telegram", {
  method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": secret }, body: JSON.stringify(body),
});

test("all shared aliases accept lowercase, uppercase and title case", () => {
  for (const command of commands) {
    for (const text of [command, command.toUpperCase(), command.replace(/\b\w/g, c => c.toUpperCase()), ` /${command} `]) {
      assert.equal(isRerun(text), true, text);
    }
  }
  for (const text of ["gO", "Go", "gO gO", " /Go   Go\n"]) assert.equal(isRerun(text), true);
  for (const text of ["don't go", "going", "hello", "go tomorrow", "??", null, {}]) assert.equal(isRerun(text), false);
});

test("authenticated go dispatches a fixed workflow before acknowledging the chat", async () => {
  const calls = [];
  const response = await handle(request(), env, async (url, options) => {
    calls.push({ url, options });
    return url.startsWith("https://api.github.com/") ? new Response(null, { status: 204 }) : Response.json({ ok: true });
  });
  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /\/telegram-webhook.yml\/dispatches$/);
  assert.deepEqual(JSON.parse(calls[0].options.body), { ref: "main", inputs: { update_id: "10" } });
  const ack = JSON.parse(calls[1].options.body);
  assert.equal(ack.chat_id, "123");
  assert.match(ack.text, /Rerun received and queued/);
});

test("missing or wrong secret fails before any external request", async () => {
  for (const secret of ["", "wrong"]) {
    assert.equal((await handle(request(update, secret), env, () => assert.fail("unauthorized fetch"))).status, 401);
  }
});

test("other chats, bots, edits and unrelated messages never dispatch", async () => {
  const variants = [
    { ...update, message: { ...update.message, chat: { id: 999 } } },
    { ...update, message: { ...update.message, from: { is_bot: true } } },
    { ...update, message: { ...update.message, text: "don't go" } },
    { update_id: 10, edited_message: update.message },
  ];
  for (const body of variants) assert.equal((await handle(request(body), env, () => assert.fail("ignored fetch"))).status, 200);
});

test("malformed or oversized updates are rejected", async () => {
  for (const update_id of [-1, "10", 1.5, null]) {
    assert.equal((await handle(request({ ...update, update_id }), env)).status, 400);
  }
  assert.equal((await handle(request({ text: "x".repeat(65537) }), env)).status, 413);
  const broken = new Request("https://example.test/telegram", {
    method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": env.WEBHOOK_SECRET }, body: "{",
  });
  assert.equal((await handle(broken, env)).status, 400);
});

test("GitHub refusal asks Telegram to retry and does not send a success acknowledgment", async () => {
  let calls = 0;
  const result = await handle(request(), env, async () => { calls++; return new Response(null, { status: 403 }); });
  assert.equal(result.status, 503);
  assert.equal(calls, 1);
});

test("Telegram acknowledgment refusal asks for retry", async () => {
  let calls = 0;
  const result = await handle(request(), env, async () => ++calls === 1 ? new Response(null, { status: 204 }) : Response.json({ ok: false }));
  assert.equal(result.status, 503);
  assert.equal(calls, 2);
});

test("network errors return a retry without echoing credentials", async () => {
  const result = await handle(request(), env, async () => { throw new Error(JSON.stringify(env)); });
  assert.equal(result.status, 503);
  assert.equal(await result.text(), "Retry later");
});

test("production entrypoint does not mistake the Workers context for fetch", async () => {
  const previous = globalThis.fetch;
  try {
    globalThis.fetch = async url => url.startsWith("https://api.github.com/") ? new Response(null, { status: 204 }) : Response.json({ ok: true });
    assert.equal((await worker.fetch(request(), env, { waitUntil() {} })).status, 200);
  } finally {
    globalThis.fetch = previous;
  }
});

test("health only reports whether the required secrets are configured", async () => {
  for (const [settings, status] of [[env, 200], [{}, 503]]) {
    const result = await worker.fetch(new Request("https://example.test/health"), settings);
    assert.equal(result.status, status);
    assert.deepEqual(await result.json(), { ready: status === 200 });
  }
});
