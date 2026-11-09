# telegram-cli

`tg` reads Alejo's personal Telegram account through the Telegram API (Telethon), logged in
as a linked device. Commands in `READ` (`src/tg/cli.py`) never change the account and never
mark messages as read; commands in `WRITE` refuse to run without `--write`. Telegram has no
read-only login: each session can do anything the account can, so the `--write` check and the
agent server's broker are the only limits. Get Alejo's confirmation of the exact message and
recipient before running `send`.

- Visibility: public. Code and 1Password references only; never commit session strings.
- Still running or billing: nothing runs on its own. Two linked devices stay signed in:
  "tg-cli Mac" and "tg-cli server" (Telegram > Settings > Devices).

## Credentials

`bin/tg` loads these through `op-agent run` from `env/mac.env` on the Mac and
`env/server.env` on the agent server. Personal 1Password account `my.1password.com`:

| Variable | Mac (vault `mac-agents`) | Server (vault `server-agents`) |
|---|---|---|
| `TG_API_ID`, `TG_API_HASH` | item `Telegram API (tg cli)`, fields `api_id`, `api_hash` | same item name and fields |
| `TG_SESSION` | item `Telegram session (tg cli, Mac)`, field `credential` | item `Telegram session (tg cli, agent server)`, field `credential` |

The API app is "alejo tg cli" at my.telegram.org. Each machine has its own session, because
one session used from two places at once gets revoked. To replace a session, revoke the old
device in Telegram, then run
`op-agent run --env-file env/mac.env -- uv run tg-login --vault mac-agents --title "Telegram session (tg cli, Mac)" --device "tg-cli Mac"`
and scan the QR code; update the item reference in the env file. A server session can be
made from the Mac without scanning: add `--code-via-session --vault server-agents --op "op --account my.1password.com"`.

## Agent server

The `agent` user runs `tg` through the credential broker (`~/best/areas/server`), which runs
`bin/tg` as `alejo` from the checkout `~/work/telegram-cli` and allows only the `READ`
commands. Deploy with `git pull` in that checkout.
