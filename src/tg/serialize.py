"""Plain dicts for users, chats and messages; keys with no value are left out."""

from telethon.tl import types as tl


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v is not False and v != []}


def name(entity) -> str:
    if isinstance(entity, tl.User):
        return " ".join(p for p in (entity.first_name, entity.last_name) if p) or "Deleted account"
    return getattr(entity, "title", None) or str(getattr(entity, "id", ""))


def kind(entity) -> str:
    if isinstance(entity, tl.User):
        return "bot" if entity.bot else "user"
    if isinstance(entity, tl.Channel):
        return "group" if entity.megagroup else "channel"
    return "group"


def user(u) -> dict:
    return _clean({"id": u.id, "name": name(u), "username": u.username, "phone": u.phone,
                   "type": kind(u), "bot": bool(u.bot)}) | {"bot": bool(u.bot)}


def media_summary(m) -> str | None:
    media = getattr(m, "media", None)
    if media is None:
        return None
    if isinstance(media, tl.MessageMediaPhoto):
        return "photo"
    if isinstance(media, tl.MessageMediaDocument) and media.document:
        for attr in media.document.attributes:
            if isinstance(attr, tl.DocumentAttributeAudio):
                return "voice" if attr.voice else "audio"
            if isinstance(attr, tl.DocumentAttributeVideo):
                return "video_note" if attr.round_message else "video"
            if isinstance(attr, tl.DocumentAttributeSticker):
                return "sticker"
            if isinstance(attr, tl.DocumentAttributeFilename):
                return f"file: {attr.file_name}"
        return "file"
    return type(media).__name__.removeprefix("MessageMedia").lower()


def action_summary(m) -> str | None:
    action = getattr(m, "action", None)
    if action is None:
        return None
    if isinstance(action, tl.MessageActionContactSignUp):
        return "joined Telegram"
    return type(action).__name__.removeprefix("MessageAction")


def message(m, sender_name: str | None = None) -> dict:
    if isinstance(m, tl.MessageEmpty):
        return {"empty": True}
    reply = getattr(m, "reply_to", None)
    return _clean({
        "id": m.id,
        "date": m.date.isoformat() if m.date else None,
        "from": sender_name,
        "out": bool(m.out),
        "text": m.message or None,
        "media": media_summary(m),
        "event": action_summary(m),
        "reply_to": getattr(reply, "reply_to_msg_id", None),
        "forwarded": bool(getattr(m, "fwd_from", None)),
        "edited": m.edit_date.isoformat() if getattr(m, "edit_date", None) else None,
    }) | {"out": bool(m.out)}


def dialog(d) -> dict:
    last = d.message
    return _clean({
        "id": d.id,
        "name": d.name or name(d.entity),
        "type": kind(d.entity),
        "unread": d.unread_count or None,
        "archived": d.folder_id == 1,
        "last_date": last.date.isoformat() if last and last.date else None,
        "last": preview(last),
    })


def preview(m, width: int = 80) -> str | None:
    if m is None:
        return None
    text = (getattr(m, "message", None) or "").replace("\n", " ")
    text = text or (f"[{action_summary(m)}]" if action_summary(m) else f"[{media_summary(m)}]" if media_summary(m) else "")
    return text if len(text) <= width else text[: width - 1] + "…"
