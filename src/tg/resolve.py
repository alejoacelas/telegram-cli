"""Turn what a person types (name, @username, t.me link, id, phone, "me") into a Telegram entity.

Resolution only reads: a phone number matches existing contacts and is never imported.
"""

import re

from telethon.tl import functions


class TgError(Exception):
    """A problem to report to the person running the command, without a traceback."""


PHONE = re.compile(r"^\+?\d[\d\s-]{6,}$")
INVITE = re.compile(r"(t\.me|telegram\.me)/(\+|joinchat/)")
LINK = re.compile(r"^(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]+)/?$")


async def resolve(client, query: str):
    q = query.strip()
    if q.lower() in ("me", "self"):
        return await client.get_me()
    if INVITE.search(q):
        raise TgError("invite links aren't supported: joining a chat is a write")
    if m := LINK.match(q):
        return await client.get_entity(m.group(1))
    if q.startswith("@"):
        return await client.get_entity(q[1:])
    if re.fullmatch(r"-?\d+", q) and not q.startswith("+"):
        return await by_id(client, int(q))
    if PHONE.match(q):
        return await by_phone(client, q)
    return await by_title(client, q)


async def by_id(client, chat_id: int):
    try:
        return await client.get_entity(chat_id)
    except ValueError:
        # A fresh string session knows no access hashes; listing dialogs teaches it them.
        await client.get_dialogs()
        try:
            return await client.get_entity(chat_id)
        except ValueError:
            raise TgError(f"no chat with id {chat_id}") from None


async def by_phone(client, phone: str):
    digits = re.sub(r"\D", "", phone)
    result = await client(functions.contacts.GetContactsRequest(hash=0))
    for user in result.users:
        if user.phone and user.phone.lstrip("+") == digits:
            return user
    raise TgError(f"no contact with phone {phone}")


async def by_title(client, title: str):
    dialogs = await client.get_dialogs()
    want = title.casefold()
    exact = [d for d in dialogs if (d.name or "").casefold() == want]
    if len(exact) == 1:
        return exact[0].entity
    partial = exact or [d for d in dialogs if want in (d.name or "").casefold()]
    if len(partial) == 1:
        return partial[0].entity
    if not partial:
        raise TgError(f'no chat named "{title}"')
    names = ", ".join(f"{d.name} ({d.id})" for d in partial[:10])
    raise TgError(f'"{title}" matches several chats; pass an id instead: {names}')
