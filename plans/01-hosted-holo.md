# Stream 1 — Prove hosted Holo

**Use this file as the entire brief for a dedicated chat.**  
Do not start streams 2–4 here. Read [SPEC.md](../SPEC.md) and [AGENTS.md](../AGENTS.md). Product law wins over this plan if they conflict.

**Start prompt for a new session:**

> Read `plans/01-hosted-holo.md`, `SPEC.md`, and `AGENTS.md`. Execute stream 1 only. Do not run Chase, llama.cpp, or private kinds. I will be at the laptop when you need Screen Recording / a desktop takeover.

---

## Goal

HoloDesktop actually drives **this Mac**. `demo_open_repo` opens the public repo in the **default browser**. The Job object stays clean (no screenshots, no HTML). We learn real Holo event types and whether `NEEDS_YOU:` / pause works.

**Done when**

- `private-desk doctor --strict` is truthful (Holo present; do not grep `holo doctor` English).
- `private-desk start demo_open_repo` → desktop moves → Job `succeeded`.
- Config `repo_url` is `https://github.com/jachian22/private-desk`.
- Redacted event log exists on disk for that job. Nothing raw pasted into chat.
- If a login/2FA/OS dialog appears: Job goes `needs_you` (token **or** quiet pause/idle). Human finishes on the laptop, `private-desk resume`, job continues or succeeds.
- If Holo types a password: **stop the line**. Do not continue to star/Chase.

**Not done:** local llama.cpp, GitHub canary in the dedicated Chrome profile, Chase.

---

## Locked decisions (do not reopen)

| Topic | Decision |
| --- | --- |
| Repo | https://github.com/jachian22/private-desk (public) |
| Browser for this stream | **Default browser**, not the `private-desk` Chrome profile |
| Inference | **Hosted** Holo. Warn: screens go to H Company. OK because public GitHub page |
| Engine | `holo_desktop.agent_client` in `src/private_desk/holo_session.py`. Not `holo run` wait-for-exit |
| Quiet pause | No `NEEDS_YOU:` token but pause/idle → still `needs_you` |
| Password field | Stop the line; fix prompt/guards |
| OTP | No `submit_otp`. No codes in chat |
| Process | Worker + `flock`. Grok Bot is not Holo’s parent |
| Logs | `holo-events.redacted.jsonl` on disk. `private-desk logs` is laptop tty only |

---

## Current code (as of this plan)

- CLI + worker exist. Dummy kind works without Holo.
- `holo_session.py` streams events, redacts, pauses on `NEEDS_YOU:` or pause-like `event.type` (`needs_you.py`).
- **Gap:** quiet/idle with no token may not yet map to `needs_you` — implement if live run shows IDLE/PAUSED without the token.
- Default `repo_url` in `config.py` is still `https://github.com` — **change default** (and README example) to `https://github.com/jachian22/private-desk`.
- `demo_open_repo.yaml`: hosted, default browser, `{repo_url}`.
- `demo_star_repo.yaml`: optional encore; needs `allow_mutating = true` + GitHub session in the **default** browser.

Install: https://hub.hcompany.ai/holo-desktop-cli and https://github.com/hcompai/holo-desktop-cli

---

## Slices (in order)

### 1a — Install and doctor

Human at the Mac.

1. Install HoloDesktop CLI (`holo` on PATH). First run may download `hai-agent-runtime` (do not vendor it).
2. macOS: Screen Recording + Accessibility for the runtime.
3. `holo login` (hosted Models API).
4. `holo doctor` on the laptop.
5. `private-desk doctor` then `private-desk doctor --strict`.
6. Code only if doctor messages are wrong or `--strict` still greps English (must not).

**Exit:** strict doctor reflects reality. Dummy still works if someone skips Holo (`doctor` without `--strict` is not a hard fail).

### 1b — Config + open-repo live

1. Ensure `~/.config/private-desk/config.toml` has `repo_url = "https://github.com/jachian22/private-desk"` (file is gitignored). Default in `config.py` / README should match so clone-and-run works without config.
2. Human: laptop free; default browser OK to take over.
3. Warn hosted screenshots go to H Company.
4. `private-desk start demo_open_repo --idempotency-key open-repo-$(date +%F)`
5. Poll `private-desk get <id>` (do not `logs` from a remote assistant).
6. Success = public repo page visible, state `succeeded`, Job JSON has no screenshot/HTML.

**Code if needed:** interpolation of `repo_url`, timeouts, `runtime_unavailable` copy.

### 1c — Event taxonomy (laptop only)

1. Find job dir: `~/.local/share/private-desk/jobs/<job_id>/`
2. Read **`holo-events.redacted.jsonl` only** in chat. Never `holo-events.raw.jsonl`.
3. Note `type` values, whether the task echo contains `NEEDS_YOU`, terminal status.
4. Write a short **redacted** note at the bottom of this plan or `plans/01-notes.local.md` (gitignored via `*.local.md` if you add it — or keep notes in the job dir). Do not commit screenshots.

### 1d — `needs_you` live

If no login wall on public GitHub, skip to “code for quiet pause” using whatever pause/idle types 1c showed.

If a wall **does** appear:

1. Job must become `needs_you` with `user_action.instruction` for the human.
2. Assistant copies instruction verbatim; does not ask for the code.
3. Human finishes on the laptop.
4. `private-desk resume <id>`
5. Holo `resume` / send_message continue; job succeeds or fails with a spec `error.code`.

**If Holo types a password:** stop. Tighten kind prompt + consider URL/allowlist. Do not add credential APIs.

**If Holo goes quiet** with pause/idle and no token: implement locked behavior in `needs_you.py` + `holo_session.py` (map those statuses to `needs_you`). Tests with fake events, not live banks.

### 1e — Optional star (same chat, after 1b)

Only if human asks and is logged into GitHub in the **default** browser.

1. `allow_mutating = true` in local config.
2. `start demo_star_repo`
3. Mutating labeled; hosted warning again.

Not required to close stream 1.

---

## Parallel (same laptop, not stream 2)

OK in this chat if it does not steal the desktop:

- Grok Bot skill from `AGENTS.md`; local computer execution **ask every time**.
- First Grok kick: `demo_dummy_files` only.
- After 1b: Grok may kick `demo_open_repo` with hosted warning.
- Mocked `AgentApiClient` tests (pause/resume/cancel) in `tests/` — no live Holo required.

Not OK: `llama-server`, GGUF, private kinds, Chase.

---

## Files you may touch

- `src/private_desk/config.py` — default `repo_url`
- `src/private_desk/needs_you.py`, `holo_session.py` — quiet pause → `needs_you`
- `src/private_desk/doctor.py` — only if 1a shows lying checks
- `README.md` — `repo_url` example
- `kinds/demo_open_repo.yaml` / `demo_star_repo.yaml` — only if live prompt fails
- `tests/test_needs_you.py` (or extend `test_doctor.py`) — classifier cases
- **Never** `kinds/` bank YAML, never commit `~/.config/private-desk/`

---

## Human checklist

- [ ] At the laptop for 1a/1b/1d
- [ ] Screen Recording + Accessibility granted
- [ ] OK with H Company seeing a public GitHub page
- [ ] Default browser may be taken over

---

## Stop / escalate

- Holo MCP installed into Grok Bot
- Binding `0.0.0.0`
- Reading PDFs or raw Holo logs into chat
- Starting stream 2–4 “while we’re here”
