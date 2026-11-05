#!/usr/bin/env python3
"""strata-router.py - strata-gw multi-model gateway (thin entry).

Scans strata-*.json in its own directory, spawns one lazy backend
(`server.py --engine strata --config <json> --lazy`) per config on its own
port, aggregates GET /v1/models over all backends, and routes every
generation request by the "model" field of its JSON body. Before a backend
loads (it was unloaded), the router unloads the other backends first, so two
models never share the machine. A 503 "GPU is in use" from a backend is
retried for a while: the other model's unload may still be in flight.
Requests that carry no model field (the web UI above all) follow the
currently resident model, so its About/Monitor pages describe the engine
that is actually running.

Adding a model: drop a strata-<model>.json next to this file, then restart
the gateway. Nothing else to register; /v1/models picks it up.
Stdlib only. The implementation lives in the gw/ package.
"""
from gw.main import main

if __name__ == "__main__":
    main()
