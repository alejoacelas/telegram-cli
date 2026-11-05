# Adapted from bssth/telegram-mcp tests/test_resolve.py (MIT, Copyright (c) 2026 Borys Stelmakh).
# Changed: a phone number matches existing contacts instead of importing one, and names match chat titles.
from types import SimpleNamespace

import pytest

from tg.resolve import TgError, resolve


class FakeClient:
    def __init__(self, contacts=(), dialogs=()):
        self.contacts = list(contacts)
        self.dialogs = list(dialogs)
        self.get_entity_args = []
        self.requests = []

    async def get_me(self):
        return "ME"

    async def get_entity(self, q):
        self.get_entity_args.append(q)
        return "ENTITY"

    async def get_dialogs(self):
        return self.dialogs

    async def __call__(self, request):
        self.requests.append(type(request).__name__)
        return SimpleNamespace(users=self.contacts)


def dialog(name, id_):
    return SimpleNamespace(name=name, id=id_, entity=f"E{id_}")


async def test_me():
    c = FakeClient()
    assert await resolve(c, "me") == "ME"
    assert await resolve(c, "self") == "ME"


async def test_username_strips_at():
    c = FakeClient()
    await resolve(c, "@durov")
    assert c.get_entity_args == ["durov"]


async def test_tme_link():
    c = FakeClient()
    await resolve(c, "https://t.me/durov")
    assert c.get_entity_args == ["durov"]


async def test_numeric_id_becomes_int():
    c = FakeClient()
    await resolve(c, "12345")
    assert c.get_entity_args == [12345]


async def test_negative_id():
    c = FakeClient()
    await resolve(c, "-100200")
    assert c.get_entity_args == [-100200]


async def test_invite_link_rejected():
    c = FakeClient()
    with pytest.raises(TgError):
        await resolve(c, "https://t.me/+AbCdEfGh")
    with pytest.raises(TgError):
        await resolve(c, "t.me/joinchat/AbCdEf")


async def test_phone_matches_contact_without_importing():
    ann = SimpleNamespace(phone="79991234567")
    c = FakeClient(contacts=[SimpleNamespace(phone="1"), ann])
    assert await resolve(c, "+7 999 123-45-67") is ann
    assert c.requests == ["GetContactsRequest"]


async def test_phone_not_found():
    c = FakeClient(contacts=[])
    with pytest.raises(TgError):
        await resolve(c, "+79991234567")


async def test_title_exact_beats_partial():
    c = FakeClient(dialogs=[dialog("Ann", 1), dialog("Annabel", 2)])
    assert await resolve(c, "ann") == "E1"


async def test_title_unique_partial():
    c = FakeClient(dialogs=[dialog("Ann Lee", 1), dialog("Bob", 2)])
    assert await resolve(c, "lee") == "E1"


async def test_title_ambiguous_lists_ids():
    c = FakeClient(dialogs=[dialog("Ann Lee", 1), dialog("Ann Ray", 2)])
    with pytest.raises(TgError, match=r"\(1\).*\(2\)"):
        await resolve(c, "ann")
