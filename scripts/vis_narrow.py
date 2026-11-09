#!/usr/bin/env python3
"""T31 narrow-face probe: measure horizontal overflow at phone widths via CDP.
Spawns headless chrome, walks the page, lists elements wider than the viewport."""
import json, subprocess, sys, time, urllib.request
import websocket

CDP_PORT = 9333
URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18092/gateway")
WIDTHS = [390, 480, 760]

PROBE = r"""
(() => {
  const vw = window.innerWidth;
  const inScroller = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.overflowX !== "visible") return true;   // clipped or swiped: legal
    }
    return false;
  };
  const offstage = (el) => {
    for (let p = el; p; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.opacity === "0" || cs.display === "none" || cs.visibility === "hidden") return true;
      if (/page|infpag/.test((p.className || "") + "") && cs.position === "absolute" &&
          cs.transform !== "none") return true;      // carousel neighbours wait offstage
    }
    return false;
  };
  const bad = [];
  document.querySelectorAll("body *").forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > vw + 2 || r.right > vw + 2) {
      if (inScroller(el) || offstage(el)) return;
      const cls = (el.id ? "#" + el.id : "") + (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).join(".") : "");
      let path = [], p = el;
      while (p && path.length < 4) { path.push(p.tagName.toLowerCase() + (p.id ? "#" + p.id : "")); p = p.parentElement; }
      bad.push({tag: el.tagName.toLowerCase(), sel: cls.slice(0, 70),
                w: Math.round(r.width), right: Math.round(r.right),
                path: path.join("<")});
    }
  });
  return {vw, docW: document.documentElement.scrollWidth,
          bodyW: document.body.scrollWidth, bad: bad.slice(0, 12)};
})()
"""

chrome = subprocess.Popen(
    ["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
     f"--remote-debugging-port={CDP_PORT}", "--window-size=390,844"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    target = None
    for _ in range(40):
        time.sleep(0.25)
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json"))
            pg = [t for t in tabs if t.get("type") == "page"]
            if pg:
                target = pg[0]["webSocketDebuggerUrl"]
                break
        except Exception:
            pass
    if not target:
        print("NO-TARGET"); sys.exit(2)
    ws = websocket.create_connection(target, timeout=20)
    nid = 0
    def send(method, **params):
        global nid
        nid += 1
        ws.send(json.dumps({"id": nid, "method": method, "params": params}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == nid:
                return msg
    send("Page.enable")
    send("Emulation.setDeviceMetricsOverride", width=WIDTHS[0], height=844,
         deviceScaleFactor=1, mobile=True)
    send("Page.navigate", url=URL)
    time.sleep(3.0)                      # let the 2s poll paint a full pass
    worst = 0
    for w in WIDTHS:
        send("Emulation.setDeviceMetricsOverride", width=w, height=844,
             deviceScaleFactor=1, mobile=True)
        time.sleep(1.2)
        r = send("Runtime.evaluate", expression=PROBE,
                 returnByValue=True)
        val = r.get("result", {}).get("result", {}).get("value") or {}
        bad = val.get("bad", [])
        print(f"W={w} docW={val.get('docW')} overflow_elems={len(bad)}")
        for b in bad[:8]:
            print(f"   {b['tag']} {b['sel']} w={b['w']} right={b['right']}")
        worst = max(worst, (val.get("docW") or 0) - w)
    print("WORST-OVERFLOW-PX", worst)
    ws.close()
finally:
    chrome.terminate()
    chrome.wait(timeout=8)
