@echo off
rem tuning.example.cmd - the engine env knobs a gateway run needs. Copy the two
rem lines into YOUR start script (or export them in the shell before launching
rem strata-router.py); gw itself does not read them, it hands them to every
rem engine it spawns. They live here precisely so a box cannot carry tuning that
rem the repo does not know about - a private start script is how tuning drifts.
rem
rem PF_FUSED      fused prefill path (keeps long prompts off the slow path)
rem PREFILL_RING  prefill slot ring size; the reference figure this repo was
rem               measured on is 384 - a smaller ring trades peak prefill
rem               throughput for RAM, a larger one the other way.
set STRATA_PF_FUSED=1
set STRATA_PREFILL_RING=384
rem
rem POSIX equivalent of the same two lines:
rem   export STRATA_PF_FUSED=1 STRATA_PREFILL_RING=384
rem   python3 strata-router.py
