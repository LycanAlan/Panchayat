"""The two requirements files must not drift apart. No AWS, no model.

requirements-prod.txt exists so the image does not ship pytest and ruff into a
container that files complaints against public bodies. The obvious way for
that to go wrong is the two files disagreeing about a version, which is a
worse problem than the one it solves -- so it is a test rather than a comment.

Owner: Kartik
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Tools the image must NOT carry. A test runner in a production container is
#: dead weight at best; at worst it is an attack surface on a box that holds
#: household data.
DEV_ONLY = ("pytest", "ruff")


def _pins(path: pathlib.Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[<>=\[]", line, maxsplit=1)[0].strip().lower()
        out[name] = line
    return out


def test_every_shared_pin_is_byte_identical():
    dev = _pins(ROOT / "requirements.txt")
    prod = _pins(ROOT / "requirements-prod.txt")

    shared = set(dev) & set(prod)
    assert shared, "the two files share nothing -- one of them is not being read"
    for name in sorted(shared):
        assert dev[name] == prod[name], (
            f"{name} drifted: requirements.txt says {dev[name]!r}, "
            f"requirements-prod.txt says {prod[name]!r}")


def test_the_runtime_file_carries_no_test_tooling():
    prod = _pins(ROOT / "requirements-prod.txt")
    for tool in DEV_ONLY:
        assert tool not in prod, f"{tool} would ship in the image"


def test_nothing_the_runtime_needs_is_missing_from_it():
    """Anything in requirements.txt that is not dev tooling has to be in the
    image, or the container builds clean and fails on the first request."""
    dev = _pins(ROOT / "requirements.txt")
    prod = _pins(ROOT / "requirements-prod.txt")

    for name in dev:
        if name in DEV_ONLY:
            continue
        assert name in prod, f"{name} is in requirements.txt but not the image"


def test_the_image_installs_the_runtime_file():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "requirements-prod.txt" in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" not in dockerfile, (
        "the image is back to installing the dev requirements")


def test_the_python_floor_is_declared():
    """numpy>=2.5.3 needs 3.12+ and nothing said so, which blocked a teammate
    before they wrote a line (issue #21)."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.12"' in pyproject


def test_pyproject_does_not_contest_ruff_toml():
    """ruff.toml is the configuration and wins over pyproject.toml -- but two
    files that both look authoritative is how the four-different-ruffs problem
    started."""
    # Section HEADERS, not any mention: the file's own comment explains why
    # there is no such section, and a substring check flagged that comment.
    headers = [line.strip() for line in
               (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
               if line.startswith("[")]
    assert not [h for h in headers if h.startswith("[tool.ruff")], headers
