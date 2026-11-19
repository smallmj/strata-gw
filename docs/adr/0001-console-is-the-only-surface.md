# Console is the only surface

Strata v0.2.16's webui gained panels (conversation cache, expert heat, queue)
and the engine page could be proxed straight through port 18075. We decided the
gw console is the **only** observation and operation surface for a multi-backend
instance — we do not embed or passthrough the engine's own webui (the browser
has no api_key through gw, the original page is single-model, and its operations
would bypass gw's confirmation gates). Engine status surfaces enter the console
verbatim through `/router/*` proxies, and gw's `/monitor` now 302s to
`/gateway#sec-monitor` instead of forwarding to a route the engine no longer
serves.

Consequence: each Strata upgrade grows the proxy set deliberately — one commit
re-pins the compat three-set (baseline, TESTED_UP_TO, sim-kit stamp) and extends
the sim kit so the new face is red-pinned before it is drawn. gw never
synthesizes engine data.

Legacy exemption (frozen, T-pinned — do not "fix"): `/` still forwards the
engine's own page when a backend is resident (bookmarks from before the
console), and 302s to `/gateway` when none is. New panels never ride that
forward — every console surface enters through `/router/*` proxies or the
catch-all; the `/` exception is kept purely for those old bookmarks.
