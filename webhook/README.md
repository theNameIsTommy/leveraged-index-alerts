# Direct Telegram receiver

Status: implemented and locally tested; hosting and a real Telegram-to-receiver-to-GitHub
acceptance run are still required. Do not report automatic replies as working from
unit tests, a green manual poll, or webhook registration alone.

## Revised path

```text
Telegram message
  -> always-available HTTPS receiver (checks secret, chat and command)
  -> GitHub workflow_dispatch accepted
  -> immediate Telegram "Rerun received and queued" acknowledgment
  -> existing Python evaluation and fresh summary
  -> shared Git state saves processed update ID and alert state
```

The receiver does not calculate signals or hold market state. The GitHub job reuses
the existing strategy, market-data adapters and BUY/SELL suppression. Both languages
read `src/leveraged_alerts/commands.json` so aliases cannot drift between receivers.
Only update IDs are forwarded to GitHub; message bodies and chat IDs are not logged
or stored in the public repository. The last 100 request IDs suppress duplicate
jobs from Telegram retries. If sending succeeds but the Git state push fails,
exactly-once delivery cannot be guaranteed; the workflow sends a failure notice.

Unknown messages, edited messages, bots and other chats are ignored. Missing or
incorrect secret headers are rejected before any external request. A GitHub or
acknowledgment delivery failure returns HTTP 503 so Telegram can retry.

## Hosting access needed

Use a Cloudflare Workers Free account with a configured `workers.dev` subdomain.
Normal personal command volume is far below the published 100,000 requests/day free
allowance. No rented server, AI call, database or extra Python service is involved.
Cloudflare credentials are not currently configured for this repository.

Configure these repository values securely in GitHub, never in source or chat:

| Kind | Name | Purpose |
| --- | --- | --- |
| Variable | `CLOUDFLARE_ACCOUNT_ID` | Chosen hosting account |
| Secret | `CLOUDFLARE_API_TOKEN` | Workers deployment permission for that account |
| Secret | `TELEGRAM_RECEIVER_GITHUB_TOKEN` | Fine-grained GitHub token limited to this repository, Actions read/write |
| Secret | `TELEGRAM_WEBHOOK_SECRET` | Cryptographically random shared secret, 32+ URL-safe characters |

The existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` stay in GitHub secrets and
are transferred directly to Worker runtime secrets during deployment. There is no
need to retrieve or paste their values. Do not reuse the broad local GitHub CLI token
as the receiver token. Track the narrow token's expiry and renew it before expiry.

## Deploy and cut over

1. Merge the receiver and workflow code into `main` after CI passes.
2. Configure the values above through GitHub's encrypted secrets/settings.
3. Run `Deploy Telegram Receiver` on `main`. It checks configuration, runs receiver
   tests, deploys with server-only secrets, checks `/health`, registers Telegram's
   webhook and verifies `getWebhookInfo` reports the expected URL. Pending Telegram
   messages are preserved, and delivery uses one connection.
4. Only after registration succeeds, the deployment disables the old polling
   workflow. It does not disable or alter the nightly alert schedule.
5. Send `gO` in the real bot chat. Verify the queued acknowledgment arrives without
   a manual dispatch, a `Telegram Webhook Rerun` job starts automatically, all assets
   are evaluated, and the fresh summary arrives.
6. Repeat once with `?`. Verify the summary arrives and old BUY/SELL alerts do not
   repeat. Separately verify a retry of the same update ID is skipped.

If deployment fails before registration, leave the existing bot configuration alone
and inspect the failure. A successful health check only proves required secret names
are populated; the real command verifies their values and permissions.

For recovery, first remove the webhook with Telegram's `deleteWebhook`, preserving
pending updates, and only then re-enable `telegram.yml`. Do not enable polling while
a webhook is active. The receiver and its narrow tokens can be revoked independently
of the nightly bot. No automatic receiver deployment runs on source pushes.

## Local checks

```bash
python -m pytest
python -m compileall -q src
node --test webhook/worker.test.mjs
npx --yes wrangler@4.156.0 deploy --dry-run --config webhook/wrangler.jsonc
```

Primary references: [Telegram webhook contract](https://core.telegram.org/bots/api#setwebhook),
[GitHub dispatch permissions](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event),
[Cloudflare free limits](https://developers.cloudflare.com/workers/platform/limits/),
[deployment action](https://github.com/cloudflare/wrangler-action).
