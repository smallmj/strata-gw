#!/usr/bin/env python3
"""test_cards.py - cards data layer: factory dossier cards, orphan/placeholder
union, persistence of POST/DELETE, and the paged-carousel markup.
Usage: python3 tests/test_cards.py    -> every assert prints PASS, ends ALL PASS."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, Stub, ok, ROUTER_PORT  # noqa: E402

MA, MB = "aaa-qwen", "bbb-sc117"          # stub backends that DO exist
A = Stub(MA, 18095)
B = Stub(MB, 18096)
gw = Gateway([MA, MB], [18095, 18096])
try:
    gw.wait_ready([MA, MB])

    s, h = gw.get("/router/cards")
    d = json.loads(h)
    ok(s == 200 and isinstance(d, dict), "C1 GET /router/cards answers 200 JSON")

    s, h = gw.get("/router/cards")
    dump = json.dumps(json.loads(h))
    ok("qwen3.8-flash-next-iq3_s" in dump and "sc117-qwen3.8-flash-next-abliterated-iq3_s" in dump,
       "C2 factory dossier cards visible out of the box")

    # union view: cards carry an orphan model no backend serves
    cd = gw.cards_file()
    cards = json.load(open(cd, encoding="utf-8"))
    cards["zzz-absent"] = {"accent": "q", "nick": {"zh": "幽灵", "en": "Ghost"},
                           "who": {"zh": "未安装的档案", "en": "an installed-elsewhere dossier"},
                           "sub": {"zh": "幽灵卡", "en": "ghost card"},
                           "tags": {"zh": [], "en": []}, "specs": {"zh": [], "en": []},
                           "style": {"zh": "", "en": ""}, "notes": {"zh": [], "en": []},
                           "art": ""}
    json.dump(cards, open(cd, "w", encoding="utf-8"), ensure_ascii=False)

    s, h = gw.get("/router/cards")
    ok("zzz-absent" in json.dumps(json.loads(h)), "C3 orphan card served even without a backend")

    html = gw.get_text("/gateway")
    ok("orphan" in html.lower() and "未安装" in html, "C4 console markup knows the orphan state")
    ok('id="pdots"' in html and 'class="deck"' in html, "C5 paged carousel markup (dots + deck)")
    ok("META={" not in html, "C6 no hardcoded dossier META baked into the page")
    ok('data-r="delcard"' in html or "delcard" in html, "C7 orphan card offers delete")
    ok('id="ed-artup"' in html and 'id="ed-artrm"' in html,
       "C7b art upload / remove tools live in the training drawer (ux v8)")
    ok('id="ed_tags"' in html and 'id="ed_lore"' in html,
       "C8 dossier editing happens through the training page drawers (ux v8)")

    # DELETE persists: gone from the file AND from the union, survives restart
    s, h = gw.delete("/router/cards/zzz-absent")
    ok(s == 200, "C9 DELETE /router/cards/<model> accepted")
    after = json.load(open(cd, encoding="utf-8"))
    ok("zzz-absent" not in after, "C10 delete wrote back to cards.json (persisted)")
    ok("zzz-absent" not in json.dumps(json.loads(gw.get_text("/router/cards"))),
       "C11 union no longer lists the deleted orphan")

    # POST merges a new dossier for a backend that had none (placeholder -> full card)
    s, h = gw.post("/router/cards", {"model": MA, "card": {
        "nick": {"zh": "小A", "en": "Little A"}, "who": {"zh": "试点特工", "en": "pilot agent"},
        "tags": {"zh": ["新档案"], "en": ["new dossier"]}, "art": ""}})
    ok(s == 200, "C12 POST /router/cards creates a dossier for the bare backend")
    now = json.load(open(cd, encoding="utf-8"))
    ok(now.get(MA, {}).get("nick", {}).get("en") == "Little A", "C13 POSTed dossier persisted to file")
    ok(MA in json.dumps(json.loads(gw.get_text("/router/cards"))), "C14 union now carries the new dossier")

    # model key sanitizing
    s, h = gw.post("/router/cards", {"model": "bad name/../x", "card": {}})
    ok(s == 400, "C15 dirty model keys rejected")

    # broken cards.json must not take the API down
    open(cd, "w", encoding="utf-8").write("{ this is not json")
    s, h = gw.get("/router/cards")
    ok(s == 200 and isinstance(json.loads(h), dict), "C16 corrupt cards.json falls back gracefully (200)")

    print("ALL PASS")
finally:
    gw.close()
    A.shutdown()
    B.shutdown()
