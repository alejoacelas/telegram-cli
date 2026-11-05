"""Log a new tg session in and store it in 1Password, without printing it.

`tg-login --vault mac-agents --op op-agent` shows a QR code; scan it in the Telegram app
(Settings > Devices > Link Desktop Device). With --code-via-session, an existing session in
TG_SESSION reads the login code Telegram sends to the account instead, so nobody scans anything.
If the account has a cloud password, a macOS dialog asks for it. The session string goes
straight into a new 1Password item.
"""

import argparse
import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import qrcode
from telethon import TelegramClient
from telethon.errors import AuthTokenExpiredError, SessionPasswordNeededError
from telethon.sessions import StringSession


def ask_password() -> str:
    script = ('text returned of (display dialog "Telegram cloud password for the tg CLI login" '
              'default answer "" with hidden answer buttons {"OK"} default button "OK")')
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
    return out.stdout.rstrip("\n")


def store(session: str, op: list[str], vault: str, title: str, who: str) -> str:
    item = {"title": title, "category": "API_CREDENTIAL", "fields": [
        {"id": "credential", "label": "credential", "type": "CONCEALED", "value": session},
        {"id": "notesPlain", "label": "notesPlain", "type": "STRING", "purpose": "NOTES",
         "value": f"Telethon StringSession for {who}, made by tg-login "
                  "(~/best/projects/2026-11-05-telegram-cli). Revoke in Telegram: Settings > Devices."}]}
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(item, f)
        # op-agent run puts a service-account token in the environment; a plain `op` would use it
        # instead of the person's own login. op-agent loads its token itself.
        env = {k: v for k, v in os.environ.items() if k != "OP_SERVICE_ACCOUNT_TOKEN"}
        out = subprocess.run([*op, "item", "create", "--vault", vault, "--template", path, "--format", "json"],
                             capture_output=True, text=True, env=env)
        if out.returncode:
            sys.exit(f"tg-login: saving the session to 1Password failed: {out.stderr.strip()}")
    finally:
        os.unlink(path)
    return json.loads(out.stdout)["id"]


async def login(args) -> None:
    client = TelegramClient(StringSession(), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"],
                            device_model=args.device, app_version="tg-cli 0.1")
    await client.connect()
    if args.code_via_session:
        await code_login(client)
    else:
        await qr_login(client)
    me = await client.get_me()
    who = f"{me.first_name or ''} (id {me.id}) on {args.device}".strip()
    item = store(client.session.save(), shlex.split(args.op), args.vault, args.title, who)
    print(f"logged in as {who}; session stored in vault {args.vault}, item {item}")
    await client.disconnect()


async def code_login(client) -> None:
    source = TelegramClient(StringSession(os.environ["TG_SESSION"]), int(os.environ["TG_API_ID"]),
                            os.environ["TG_API_HASH"], receive_updates=False)
    await source.connect()
    try:
        phone = (await source.get_me()).phone
        asked = datetime.now(timezone.utc) - timedelta(seconds=5)
        sent = await client.send_code_request(phone)
        code = None
        for _ in range(30):
            for m in await source.get_messages(777000, limit=3):
                found = re.search(r"\b(\d{5,6})\b", m.message or "")
                if m.date >= asked and found:
                    code = found.group(1)
                    break
            if code:
                break
            await asyncio.sleep(2)
        if not code:
            sys.exit("tg-login: no login code arrived in the Telegram service chat")
        try:
            await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
        except SessionPasswordNeededError:
            await client.sign_in(password=ask_password())
    finally:
        await source.disconnect()


async def qr_login(client) -> None:
    qr = await client.qr_login()
    folder = tempfile.mkdtemp(prefix="tg-login-")
    for attempt in range(12):  # each code lives about 30 seconds
        # A new file name each time: Preview keeps showing a file's old image after it changes.
        png = os.path.join(folder, f"scan-this-{attempt + 1}.png")
        qrcode.make(qr.url, box_size=12).save(png)
        subprocess.run(["open", "-a", "Preview", png])
        try:
            await qr.wait(timeout=max(5, (qr.expires - datetime.now(timezone.utc)).total_seconds() - 2))
            break
        except (asyncio.TimeoutError, AuthTokenExpiredError):
            await qr.recreate()
        except SessionPasswordNeededError:
            await client.sign_in(password=ask_password())
            break
    else:
        sys.exit("tg-login: QR code was not scanned in time")
    subprocess.run(["osascript", "-e", 'tell application "Preview" to close (every window whose name starts with "scan-this-")'])
    shutil.rmtree(folder)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vault", required=True, help="1Password vault for the new session item")
    p.add_argument("--op", default="op-agent", help="1Password CLI command that can write to the vault")
    p.add_argument("--title", default="Telegram session (tg cli)")
    p.add_argument("--code-via-session", action="store_true",
                   help="read the login code with the existing session in TG_SESSION instead of a QR code")
    p.add_argument("--device", default="tg-cli", help="device name shown in Telegram's Devices list")
    asyncio.run(login(p.parse_args()))
