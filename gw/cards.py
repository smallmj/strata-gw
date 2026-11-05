"""cards.py - per-model persona dossier cards, persisted in cards/cards.json.

Design rule: technical facts (ports, context, quant, cache sizes...) are
NEVER stored here - the console renders them live from /router/backends and
/router/info so a card can never go stale against the user's actual setup.
This file holds only the user-editable persona fields (nick/who/sub/tags/
style/notes/lore/art/accent), each as {zh,en} where text is involved.

Union view lives in the front-end: console cards = backend models ∪ card keys.
A card with no backend = orphan ("not installed", deletable); a backend with
no card = placeholder ("edit dossier" creates one on the spot).
"""
from __future__ import annotations

import json
import os
import re

from . import config

CARDS_PATH = os.path.join(config.ROOT, "cards", "cards.json")
MODEL_KEY = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# ---- uploaded art (card portraits and the pet share this pipeline) -------
UPLOAD_DIR = os.path.join(config.ROOT, "gw-assets", "uploads")
UPLOAD_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}\.(?:png|jpe?g|webp)$")
MAX_UPLOAD = 5_242_880                       # 5 MiB, per spec


def sniff_image(data: bytes):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def parse_multipart(body: bytes, content_type: str):
    """Minimal stdlib multipart reader: returns (raw_filename, bytes) of the
    first 'file' part, or None."""
    m = re.search(r'boundary="?([^";\r\n]+)"?', content_type or "")
    if not m:
        return None
    sep = b"--" + m.group(1).encode()
    for part in body.split(sep):
        if part.startswith(b"--") or b"\r\n\r\n" not in part:
            continue
        head, data = part.split(b"\r\n\r\n", 1)
        if b'name="file"' not in head:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        fm = re.search(rb'filename="([^"]*)"', head)
        return (fm.group(1).decode("utf-8", "replace") if fm else ""), data
    return None


def handle_upload(raw_name: str, data: bytes):
    """Validate + store an upload. Extension is normalized to the sniffed
    real type (bytes beat names); collisions get a time suffix, then a counter.
    Returns (status, response)."""
    if "/" in raw_name or "\\" in raw_name or ".." in raw_name:
        return 400, {"error": {"message": "bad file name (no paths please)"}}
    name = raw_name.strip().lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ("png", "jpg", "jpeg", "webp"):
        return 415, {"error": {"message": "unsupported content type (png/jpg/jpeg/webp only)"}}
    real = sniff_image(data)
    if real is None:
        return 415, {"error": {"message": "magic bytes do not match an image (png/jpeg/webp) content rejected"}}
    if len(data) > MAX_UPLOAD:
        return 413, {"error": {"message": "too large (max 5 MB)"}}
    stem = re.sub(r"[^a-z0-9_-]+", "-", name.rsplit(".", 1)[0])[:40].strip("-_") or "art"
    fname = f"{stem}.{real}"
    if not UPLOAD_NAME.match(fname):
        return 400, {"error": {"message": "bad file name"}}
    import time as _t
    if os.path.exists(os.path.join(UPLOAD_DIR, fname)):
        fname = f"{stem}-{_t.strftime('%H%M%S')}.{real}"
        n = 1
        while os.path.exists(os.path.join(UPLOAD_DIR, fname)) and n < 100:
            fname = f"{stem}-{_t.strftime('%H%M%S')}-{n}.{real}"
            n += 1
    if not UPLOAD_NAME.match(fname):
        return 400, {"error": {"message": "bad file name"}}
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
            f.write(data)
    except OSError as e:
        print(f"[router] upload store failed: {e}", flush=True)
        return 500, {"error": {"message": "could not store the file"}}
    return 200, {"art": f"router/uploads/{fname}", "bytes": len(data)}


def load_cards() -> dict:
    """Read cards.json; BOM-tolerant; a corrupt file degrades to {} (with a
    log line) rather than taking the console down."""
    try:
        with open(CARDS_PATH, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except OSError as e:
        print(f"[router] cards.json unreadable: {e}", flush=True)
        return {}
    except ValueError as e:
        print(f"[router] cards.json is not valid json: {e}", flush=True)
        return {}


def _save(cards: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(CARDS_PATH), exist_ok=True)
        tmp = CARDS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, CARDS_PATH)
        return True
    except OSError as e:
        print(f"[router] cannot write cards.json: {e}", flush=True)
        return False


def merge_card(model: str, card: dict) -> tuple[int, dict]:
    """Merge a card's fields onto the stored entry (per top-level key).
    Returns (status, response)."""
    if not MODEL_KEY.match(model or ""):
        return 400, {"error": {"message": "bad model key (allowed: [A-Za-z0-9._-]{1,64})"}}
    if not isinstance(card, dict):
        return 400, {"error": {"message": "card must be an object"}}
    cards = load_cards()
    stored = cards.get(model)
    entry = stored if isinstance(stored, dict) else {}
    for k, v in card.items():
        if v is None:
            entry.pop(k, None)
        else:
            entry[k] = v
    cards[model] = entry
    if not _save(cards):
        return 500, {"error": {"message": "could not persist cards.json"}}
    return 200, {"ok": True, "model": model}


def delete_card(model: str) -> tuple[int, dict]:
    if not MODEL_KEY.match(model or ""):
        return 400, {"error": {"message": "bad model key"}}
    cards = load_cards()
    if model not in cards:
        return 404, {"error": {"message": "no such card"}}
    cards.pop(model)
    if not _save(cards):
        return 500, {"error": {"message": "could not persist cards.json"}}
    return 200, {"ok": True, "deleted": model}
