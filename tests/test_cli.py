import ast
from pathlib import Path

import pytest

from tg import cli


@pytest.mark.parametrize("argv", [
    ["send", "me", "hi"], ["mark-read", "me"], ["archive", "me"], ["unarchive", "me"],
    ["archive-joined"], ["joined-alerts", "off"],
])
def test_writes_refused_without_flag(argv, monkeypatch):
    # Refused before any connection: no credentials are set, so connecting would fail differently.
    for k in ("TG_API_ID", "TG_API_HASH", "TG_SESSION"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit, match="--write"):
        cli.main(argv)


def test_every_subcommand_is_classified():
    sub = next(a for a in cli.parser()._actions if a.dest == "command")
    assert set(sub.choices) == cli.READ | cli.WRITE
    assert not cli.READ & cli.WRITE


def test_every_json_dumps_call_keeps_non_ascii_text():
    # Adapted from chigwell/telegram-mcp tests/test_json_unicode.py (Apache-2.0).
    package = Path(cli.__file__).parent
    missing = []
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "dumps"
                    and getattr(node.func.value, "id", None) == "json"
                    and not any(k.arg == "ensure_ascii" for k in node.keywords)):
                missing.append(f"{path.name}:{node.lineno}")
    assert missing == []
