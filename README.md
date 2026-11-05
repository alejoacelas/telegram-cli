# telegram-cli

`tg`, a command-line client for Alejo's personal Telegram account. It reads by default;
commands that change the account need `--write`.

```sh
bin/tg chats --unread
bin/tg read "Daniel Zambrano" -n 20
bin/tg search "invoice"
bin/tg --write send @someone "hi"
```

Run `bin/tg --help` for every command. Tests: `uv run pytest`.
