#!/usr/bin/env python3
"""test_upload.py - uploaded art (card portraits + pet share one endpoint):
multipart parsing, whitelist extensions + magic-number sniffing, size caps,
name sanitizing, collision suffixes, Range/ETag serving and DELETE.
Usage: python3 tests/test_upload.py    -> PASS lines, ALL PASS, exit 0."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stub_common import Gateway, Stub, ok, ROUTER_PORT  # noqa: E402

MA = "aaa-qwen"
A = Stub(MA, 18095)
gw = Gateway([MA], [18095])

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 4 + b"IHDR" + b"\x11" * 400)
JPEG = b"\xff\xd8\xff\xe0" + b"\x22" * 300
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x33" * 200


def upload(fname, blob, extra_hdrs=None):
    """Build a minimal multipart/form-data POST by hand (stdlib only)."""
    boundary = "----stgwtestboundary7365"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + blob + \
           f"\r\n--{boundary}--\r\n".encode()
    hdrs = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if extra_hdrs:
        hdrs.update(extra_hdrs)
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=15)
    c.request("POST", "/router/upload", body=body, headers=hdrs)
    r = c.getresponse()
    data = r.read().decode("utf-8", "replace")
    c.close()
    return r.status, data


try:
    gw.wait_ready([MA])

    s, h = upload("a.webp", PNG)   # right bytes, "wrong" display extension - sniffing wins
    j = json.loads(h)
    ok(s == 200 and j.get("art", "").startswith("router/uploads/a"),
       "U1 upload accepted -> 200 {\"art\":\"router/uploads/...\"}")
    art = j.get("art", "")
    name = art.split("/")[-1]

    s, body, loc, ctype = gw.raw("GET", "/router/uploads/" + name)
    ok(s == 200 and body == PNG and ctype == "image/png",
       "U2 uploaded bytes served back identical (sniffed png despite .webp name)")

    big = b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024 + 1)
    s, h = upload("b.png", big)
    ok(s == 413 and "too large" in h, "U3 5MiB+1 rejected 413 too large (max 5 MB)")

    s, h = upload("c.png", b"MZ" + b"\x90\x00" + b"\x00" * 100)
    ok(s == 415 and ("magic" in h or "content" in h or "sniff" in h),
       "U4 right extension wrong magic rejected 415")

    s, h = upload("d.txt", PNG)
    ok(s == 415, "U5 non-whitelisted extension rejected 415")

    s, h = upload("../evil.png", PNG)
    ok(s in (400, 415) and ".." not in json.loads(h).get("art", ""),
       "U6 path traversal in filename rejected/sanitized")

    s, h1 = upload("same.png", PNG)
    s2, h2 = upload("same.png", JPEG)
    n1 = json.loads(h1).get("art", "").split("/")[-1]
    n2 = json.loads(h2).get("art", "").split("/")[-1]
    ok(s == 200 and s2 == 200 and n1 != n2,
       "U7 same-name collision auto-suffixed, both stored")

    # Range + ETag on uploads too (asset-serving parity)
    c_name = json.loads(h2).get("art", "").split("/")[-1]
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=15)
    c.request("GET", "/router/uploads/" + c_name, headers={"Range": "bytes=0-9"})
    r = c.getresponse()
    body = r.read()
    etag = r.getheader("ETag") or ""
    ok(r.status == 206 and len(body) == 10 and (r.getheader("Content-Range") or "").endswith(
        "/" + str(len(JPEG))), "U8 uploads serve Range slices (206 + Content-Range)")
    c = http.client.HTTPConnection("127.0.0.1", ROUTER_PORT, timeout=15)
    c.request("GET", "/router/uploads/" + c_name, headers={"If-None-Match": etag})
    r = c.getresponse()
    r.read()
    ok(r.status == 304, "U9 uploads revalidate with ETag -> 304")
    c.close()

    s, h = gw.delete("/router/uploads/" + name)
    ok(s == 200, "U10 DELETE /router/uploads/<name> ok")
    s, body, loc, ctype = gw.raw("GET", "/router/uploads/" + name)
    ok(s == 404, "U11 deleted upload 404")

    s, body, loc, ctype = gw.raw("GET", "/router/uploads/..%2Fcards.json")
    ok(s == 404, "U12 uploads traversal blocked")

    print("ALL PASS")
finally:
    gw.close()
    A.shutdown()
