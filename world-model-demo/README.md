# World Model Demo

This folder contains a small demo that probes whether the current AiBrain
backend can already support a lightweight world model.

What it uses:

- `backend/logs/main_brain/brain_runs.jsonl`
- procedural memory collection, preview mining, and template matching
- semantic memory search
- entity graph expansion
- scene graph and scene diffusion
- incremental causal writing with an LLM-first writer plus deterministic
  fallback
- a small built-in causal seed overlay in `world-model-demo/data/causal_seed_relations.jsonl`

What it is not:

- not a new production subsystem
- not a full simulator
- not an LLM replacement

## Run

From the repo root:

```powershell
python .\world-model-demo\demo.py
```

Useful variations:

```powershell
python .\world-model-demo\demo.py --query "世界模型 后果 预测"
python .\world-model-demo\demo.py --run-id bg_20260620T062834.1883160000_7fa2
python .\world-model-demo\demo.py --json
python .\world-model-demo\demo.py --output .\world-model-demo\report.json
python .\world-model-demo\demo.py --sync-causal --causal-max-new-runs 1
python .\world-model-demo\demo.py --query "proactive_contact create_pending"
```

## What To Look At

- `latest_run`: the latest run summary read from `brain_runs.jsonl`
- `procedural`: collected examples, mined template preview, and current matches
- `memory`: semantic memory hits from the backend memory layer
- `graph`: entity graph evidence and related memories
- `scene`: scene graph / diffusion candidates
- `prediction`: the final short-horizon world-model judgment
- `capability`: a quick verdict on whether the current backend already has
  enough structure to support a lightweight world model

## Notes

- The script is defensive. If one backend subsystem is unavailable, it keeps
  going and reports partial coverage instead of crashing.
- The goal is to validate the architecture: `event -> memory -> relation ->
  prediction`.
- Causal data is written incrementally into `world-model-demo/data/` so the
  demo can reuse earlier extracted relations on the next run.
- Seed relations are loaded from `world-model-demo/data/causal_seed_relations.jsonl`
  so the demo can be tested even before enough live causal data accumulates.
- If you want, this demo can later be promoted into a formal backend route or
  benchmark harness.
