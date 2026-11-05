"""tg: read Telegram from the command line. Commands that change anything need --write.

Reading never marks messages as read. Credentials come from TG_API_ID, TG_API_HASH and
TG_SESSION; the bin/tg launcher loads them from 1Password.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import functions
from telethon.tl import types as tl

from . import serialize
from .resolve import TgError, resolve

READ = {"me", "chats", "read", "search", "joined"}
WRITE = {"send", "mark-read", "archive", "unarchive", "archive-joined", "joined-alerts"}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tg", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    p.add_argument("--write", action="store_true", help="allow commands that change your account")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sub.add_parser("me", help="the logged-in account")
    c = sub.add_parser("chats", help="list chats, most recent first")
    c.add_argument("-n", "--limit", type=int, default=30)
    c.add_argument("--unread", action="store_true", help="only chats with unread messages")
    c.add_argument("--archived", action="store_true", help="the Archive folder instead of the main list")
    r = sub.add_parser("read", help="messages in one chat, oldest first")
    r.add_argument("chat", help="name, @username, t.me link, id, phone or 'me'")
    r.add_argument("-n", "--limit", type=int, default=30)
    r.add_argument("--since", help="only messages on or after this date (YYYY-MM-DD)")
    r.add_argument("--before", type=int, help="only messages older than this message id")
    s = sub.add_parser("search", help="search messages across chats, or in one with --chat")
    s.add_argument("query")
    s.add_argument("--chat")
    s.add_argument("-n", "--limit", type=int, default=30)
    j = sub.add_parser("joined", help="chats holding nothing but an 'X joined Telegram' notice")
    j.add_argument("--archived", action="store_true", help="look in the Archive folder instead")

    w = sub.add_parser("send", help="[write] send a message; TEXT '-' reads standard input")
    w.add_argument("chat")
    w.add_argument("text")
    w.add_argument("--reply-to", type=int)
    m = sub.add_parser("mark-read", help="[write] mark a chat as read")
    m.add_argument("chat")
    for verb in ("archive", "unarchive"):
        a = sub.add_parser(verb, help=f"[write] {verb} chats")
        a.add_argument("chats", nargs="+")
    sub.add_parser("archive-joined", help="[write] archive every chat that `tg joined` lists")
    ja = sub.add_parser("joined-alerts", help="[write] turn 'contact joined Telegram' notifications on or off")
    ja.add_argument("state", choices=["on", "off"])
    return p


def client_from_env() -> TelegramClient:
    missing = [k for k in ("TG_API_ID", "TG_API_HASH", "TG_SESSION") if not os.environ.get(k)]
    if missing:
        raise TgError(f"missing {', '.join(missing)}; run tg through bin/tg, which loads them from 1Password")
    return TelegramClient(StringSession(os.environ["TG_SESSION"]), int(os.environ["TG_API_ID"]),
                          os.environ["TG_API_HASH"], receive_updates=False, flood_sleep_threshold=120)


def out(args, rows, text):
    """Print rows as JSON with --json, otherwise one line per row through text()."""
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for row in rows if isinstance(rows, list) else [rows]:
            print(text(row))


async def joined_only(client, archived: bool):
    """Private chats whose whole history is 'joined Telegram' notices."""
    found = []
    async for d in client.iter_dialogs(folder=1 if archived else 0):
        if not d.is_user or not isinstance(getattr(d.message, "action", None), tl.MessageActionContactSignUp):
            continue
        history = await client.get_messages(d.entity, limit=5)
        if all(isinstance(getattr(m, "action", None), tl.MessageActionContactSignUp) for m in history):
            found.append(d)
    return found


async def set_archived(client, entities, archived: bool):
    peers = [tl.InputFolderPeer(peer=await client.get_input_entity(e), folder_id=1 if archived else 0) for e in entities]
    for i in range(0, len(peers), 100):
        await client(functions.folders.EditPeerFoldersRequest(folder_peers=peers[i:i + 100]))


async def run(args) -> None:
    client = client_from_env()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise TgError("the session is no longer valid; log in again with tg-login")
        await dispatch(client, args)
    finally:
        await client.disconnect()


async def dispatch(client, args) -> None:
    cmd = args.command
    if cmd == "me":
        me = serialize.user(await client.get_me())
        out(args, me, lambda u: f"{u['name']} (@{u.get('username', '-')}, id {u['id']})")

    elif cmd == "chats":
        rows = []
        async for d in client.iter_dialogs(folder=1 if args.archived else 0):
            if args.unread and not d.unread_count:
                continue
            rows.append(serialize.dialog(d))
            if len(rows) >= args.limit:
                break
        out(args, rows, lambda r: "\t".join([str(r["id"]), r["name"], f"unread {r['unread']}" if r.get("unread") else "",
                                             r.get("last_date", "")[:16], r.get("last", "")]))

    elif cmd == "read":
        entity = await resolve(client, args.chat)
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else None
        msgs = []
        async for m in client.iter_messages(entity, limit=args.limit, max_id=args.before or 0):
            if since and m.date < since:
                break
            msgs.append(serialize.message(m, serialize.name(m.sender) if m.sender else None))
        msgs.reverse()
        out(args, msgs, line)

    elif cmd == "search":
        entity = await resolve(client, args.chat) if args.chat else None
        rows = []
        async for m in client.iter_messages(entity, search=args.query, limit=args.limit):
            row = serialize.message(m, serialize.name(m.sender) if m.sender else None)
            chat = await m.get_chat()
            rows.append({"chat": serialize.name(chat) if chat else None, "chat_id": m.chat_id} | row)
        out(args, rows, lambda r: f"{r['chat']} ({r['chat_id']}) | " + line(r).replace("\n", " / "))

    elif cmd == "joined":
        rows = [{"id": d.id, "name": d.name, "date": d.message.date.isoformat()} for d in await joined_only(client, args.archived)]
        out(args, rows, lambda r: f"{r['id']}\t{r['name']}\t{r['date'][:10]}")

    elif cmd == "send":
        entity = await resolve(client, args.chat)
        text = sys.stdin.read() if args.text == "-" else args.text
        m = await client.send_message(entity, text, reply_to=args.reply_to)
        out(args, {"sent": m.id, "to": serialize.name(entity)}, lambda r: f"sent message {r['sent']} to {r['to']}")

    elif cmd == "mark-read":
        entity = await resolve(client, args.chat)
        await client.send_read_acknowledge(entity)
        out(args, {"read": serialize.name(entity)}, lambda r: f"marked {r['read']} as read")

    elif cmd in ("archive", "unarchive"):
        entities = [await resolve(client, c) for c in args.chats]
        await set_archived(client, entities, cmd == "archive")
        out(args, [serialize.name(e) for e in entities], lambda n: f"{cmd}d {n}")

    elif cmd == "archive-joined":
        found = await joined_only(client, archived=False)
        await set_archived(client, [d.entity for d in found], True)
        out(args, {"archived": len(found)}, lambda r: f"archived {r['archived']} 'joined Telegram' chats")

    elif cmd == "joined-alerts":
        await client(functions.account.SetContactSignUpNotificationRequest(silent=args.state == "off"))
        out(args, {"joined_alerts": args.state}, lambda r: f"'contact joined Telegram' notifications {r['joined_alerts']}")


def line(m: dict) -> str:
    body = m.get("text") or ""
    extra = " ".join(f"[{m[k]}]" for k in ("media", "event") if m.get(k))
    who = "me" if m.get("out") else m.get("from", "?")
    return f"{m.get('date', '')[:16]} #{m['id']} {who}: {(extra + ' ' + body).strip()}"


def main(argv=None) -> None:
    args = parser().parse_args(argv)
    if args.command in WRITE and not args.write:
        sys.exit(f"tg: `{args.command}` changes your account; rerun with --write")
    try:
        asyncio.run(run(args))
    except TgError as e:
        sys.exit(f"tg: {e}")
