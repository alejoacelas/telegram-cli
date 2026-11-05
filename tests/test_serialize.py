# Adapted from bssth/telegram-mcp tests/test_serialize.py (MIT, Copyright (c) 2026 Borys Stelmakh).
from datetime import datetime, timezone
from types import SimpleNamespace

from telethon.tl import types as tl

from tg import serialize


def msg(**kw):
    base = dict(id=5, date=None, message="hi", out=True, reply_to=None, edit_date=None,
                fwd_from=None, media=None, action=None)
    return SimpleNamespace(**(base | kw))


def test_user():
    u = tl.User(id=42, first_name="Ann", last_name="Lee", username="ann", phone="123")
    d = serialize.user(u)
    assert d["id"] == 42
    assert d["name"] == "Ann Lee"
    assert d["username"] == "ann"
    assert d["type"] == "user"
    assert d["bot"] is False


def test_message_basic():
    d = serialize.message(msg(), "Ann")
    assert d["id"] == 5
    assert d["text"] == "hi"
    assert d["out"] is True
    assert d["from"] == "Ann"
    assert "media" not in d  # empty fields are left out


def test_message_incoming_keeps_out_false():
    assert serialize.message(msg(out=False))["out"] is False


def test_message_empty():
    assert serialize.message(tl.MessageEmpty(id=0, peer_id=None)) == {"empty": True}


def test_media_summary_none():
    assert serialize.media_summary(SimpleNamespace(media=None)) is None


def test_joined_notice_is_an_event():
    d = serialize.message(msg(message="", action=tl.MessageActionContactSignUp(),
                              date=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    assert d["event"] == "joined Telegram"
    assert "text" not in d
    assert serialize.preview(msg(message="", action=tl.MessageActionContactSignUp())) == "[joined Telegram]"
