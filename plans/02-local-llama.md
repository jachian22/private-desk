# Stream 2 — Local llama.cpp (pet)

**Use this file as the entire brief for a dedicated chat.**  
Do not run Chase or the GitHub session canary here (those are streams 3–4). Hosted Holo proof is stream 1. Read [SPEC.md](../SPEC.md) and [AGENTS.md](../AGENTS.md).

**Start prompt for a new session:**

> Read `plans/02-local-llama.md`, `SPEC.md`, and `AGENTS.md`. Execute stream 2 only. llama.cpp is a pet: never spawn `llama-server`. Improve doctor/`start` UX so a missing server is obvious. GGUF download may already be in progress.

You may **start the GGUF download immediately** even if stream 1 is unfinished.

---

## Goal

A local OpenAI-compatible server on **loopback** serves Holo 3.1. `private-desk` points at it. Bank/canary kinds can require `inference: local`. Humans are told in plain language when the pet is not running.

**Done when**

- Q4 GGUF for `Hcompany/Holo-3.1-35B-A3B-GGUF` is on disk (~21 GB).
- `llama-server` listens on `http://127.0.0.1:8080/v1` (not `0.0.0.0`).
- `private-desk doctor` shows `local_model: reachable` when the pet is up, and a **clear “boot llama-server” note** when it is not (not only `unreachable`).
- `start` of a **local** Holo kind while the pet is down fails with a message that includes how to start the server (still no spawn).
- `~/.config/private-desk/config.toml` has `holo_base_url` + `holo_model` (gitignored).
- README documents the H Company Mac recipe as the known-good path; LM Studio is optional via same `holo_base_url`.

**Not done:** GitHub canary, Chase, auto-starting llama.cpp, daemon.

---

## Locked decisions (do not reopen)

| Topic | Decision |
| --- | --- |
| Process | **Pet.** User starts `llama-server`. We never fork it from `start` |
| UX | Doctor + local-kind `start` must say they need to boot the server, with a copy-pasteable command |
| Bind | Loopback only. Do not bind `0.0.0.0` |
| Hardware | M4 Max; Q4 ~21 GB weights + KV cache is expected to fit |
| Engine | Any OpenAI-compatible server at `holo_base_url`. Default recipe: llama.cpp, not LM Studio |
| Hosted | Still OK for `demo_open_repo` / `demo_star_repo` only |
| Local kinds | `inference: local` on the kind wins; cannot “fall back” to hosted for GitHub canary / Chase |

Recipe: [Run a local model server](https://hub.hcompany.ai/holo-desktop-cli/how-to/run-a-local-model-server)

---

## Current code (as of this plan)

- `doctor.py` `_local_model()` GETs `{holo_base_url}/models`. Sets `local_model` / `llama_cpp` to `reachable` | `unreachable`. Notes mention llama.cpp but **do not tell you the start command**.
- `start_job` checks `holo_ready()` (binary / `holo_desktop` import). It does **not** check loopback `/v1/models` before kicking a local kind.
- `holo_session.py` passes `SpawnConfig(base_url=..., model=...)` when `job["inference"] == "local"`.
- Default `holo_base_url`: `http://127.0.0.1:8080/v1`, `holo_model`: `holo3-1-35b`.

---

## Slices

### 2a — Weights (long-running, unattended OK)

1. `brew install llama.cpp` if needed.
2. Download official GGUF: `Hcompany/Holo-3.1-35B-A3B-GGUF` (Q4_K_M class; ~21 GB). `llama-server -hf ...` may pull it.
3. Confirm disk space before starting. Do not commit `*.gguf` (gitignore).

**Exit:** file exists on disk. Server need not stay up 24/7.

### 2b — Serve on loopback

Use H Company’s Mac flags (Metal, Q4). **`--host 127.0.0.1`** (or default localhost). Port 8080.

Smoke: `curl -sS http://127.0.0.1:8080/v1/models`

If the user prefers LM Studio later: same URL in config; do not make it the documented default.

### 2c — Config

Create/update `~/.config/private-desk/config.toml` (never commit):

```toml
inference = "local"
holo_bin = "holo"
holo_base_url = "http://127.0.0.1:8080/v1"
holo_model = "holo3-1-35b"
repo_url = "https://github.com/jachian22/private-desk"
browser_profile = "private-desk"
allow_mutating = false
```

`doctor` without `--strict` still succeeds if Holo is missing; local_model may be unreachable.

### 2d — UX: pet is down (required code)

When `local_model` is unreachable:

**Doctor notes** (plain language), e.g.:

- Local model is not running.
- Bank and session-canary kinds need `llama-server` at `holo_base_url`.
- Example: `llama-server --hf Hcompany/Holo-3.1-35B-A3B-GGUF` (plus documented tuning flags from H Company). Point `--host` at 127.0.0.1.

**`start` of a kind with resolved `inference == local` and `runner == holo`:**

- Probe `/v1/models` first (same helper as doctor).
- If down: do **not** create a job. Error code `runtime_unavailable` or `model_error` (pick one, use it consistently; prefer `runtime_unavailable`).
- `error.message`: short, **includes that llama-server must be started**, not a stack trace.

Hosted kinds (`demo_open_repo`) must **not** require the pet.

Tests: mock unreachable URL; `start` of a local kind fails without a worker; hosted kind still only requires `holo_ready`.

### 2e — Local smoke (non-bank)

After 2b is up: one hosted-vs-local sanity check **without Chase**.

Options:

- Run a trivial local Holo task if stream 1 already proved hosted (open a public page) **or**
- Wait for stream 3 for GitHub-in-profile.

Do not download statements. Do not use hosted inference “just this once” for a canary/bank kind.

---

## Files you may touch

- `src/private_desk/doctor.py` — notes + maybe structured `local_model_hint`
- `src/private_desk/api.py` — preflight local kinds
- Share the probe helper (don’t duplicate curl logic forever)
- `README.md` — llama.cpp recipe, pet UX, LM Studio one-liner
- `tests/test_doctor.py` + start preflight tests with a fake kind `inference: local` **or** monkeypatch `resolve_inference`
- **Never** commit GGUF, never spawn llama.cpp, never `0.0.0.0`

---

## Human checklist

- [ ] ~25 GB free disk
- [ ] Willing to leave `llama-server` running while doing local jobs (RAM)
- [ ] Not expecting Grok Bot cron to boot the model

---

## Stop / escalate

- Auto-start llama.cpp “to be nice”
- Binding all interfaces
- Using hosted Holo for anything with a real account
- Starting Chase in this chat
