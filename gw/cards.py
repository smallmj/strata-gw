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
