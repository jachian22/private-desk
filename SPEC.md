# private-desk — spec v0

Hand this to a code agent. It is a **control-plane** spec, not a computer-use spec.

Protocol id: `private-desk/v0`

License: **Apache-2.0** (same as HoloDesktop CLI). Do not vendor, relicense, or redistribute `hai-agent-runtime`; that binary is H Company’s, downloaded by `holo`.

CLI / product name: **`private-desk`**.

---

## 1. What this is

A privacy-preserving job control plane on the user’s laptop. A consumer assistant (Grok Bot first) can **kick off** one allowlisted desktop job and learn how it went. It never gets eyes or hands on the desktop: no screenshots, HTML, cookies, PDFs, balances, account numbers, or OTPs.

**HoloDesktop is the engine.** We name it. We do not expose Holo’s click / screenshot / `holo run` / MCP surface to the assistant. That is the product.

**Who it is for**

- Personal use (e.g. Chase statement download on this Mac)
- Open source: demo loop + kind format, FDE/portfolio story around H Company’s stack plus a real trust boundary
- Grok Bot as the first consumer shape; other assistants later via the same CLI kick

**Core idea.** Grok Bot (or any kicker) **dispatches**. A **laptop job worker** does the work. The chat command is a kick, not a parent. If the bot dies, the job does not.

---

## 2. Goals and non-goals

**Goal.** One allowlisted Holo job at a time on the user’s waking desktop. The assistant sees only the Job object. Artifacts stay on disk.

**Non-goals**

- Giving the assistant eyes or hands on the desktop
- Free-form “do anything on my computer”
- Shipping statement contents, OCR, or screenshots to Grok Bot
- Hosted Holo inference for bank / login kinds (H Company would see the screen)
- Moving money, paying bills, submitting transfers
- Assistant- or worker-held bank passwords, OTP codes, or stolen cookies
- 1Password / Keychain / cookie-export integrations in v1
- Always-on daemon, inbound Grok Bot webhooks, or remote MCP in v1
- Auto-starting `may_need_you` jobs from a Grok Bot cron while the lid is closed

---

## 3. Trust boundary

Treat every byte coming out of the CUA runtime as untrusted. The only object CLI JSON (and later MCP/webhooks) may return is the **Job** schema below.

Redaction gateway between Holo and anything assistant-facing:

- Drop screenshots, video, DOM, HAR, cookies, headers, clipboard, keystrokes
- Drop file contents. Paths and filenames are ok
- Drop numbers that look like amounts, account numbers, routing numbers, SSNs, card PANs, OTPs
- Drop raw Holo logs. Persist them under the job dir locally; never return them
- `error.message` is a short class string, not an exception dump and not OCR from the page

### Three observers

| Who | Sees bank / login screens? | Stance |
| --- | --- | --- |
| Grok Bot / remote assistant | No | Job object only |
| H Company Models API | Yes, if hosted | Allowed for **public demo kinds** and labeled. **Forbidden** for bank, login, and session-canary kinds that hit real accounts |
| Local Holo + `hai-agent-runtime` | Yes, on this machine | Inherent to computer-use. “Private” means it does not leave the machine |

Credentials live in the OS keychain / the user’s real browser profile (and 1Password in the browser, if they use it). The assistant never passes `password`, `otp`, `cookie`, `token`, or `session` params. The worker never calls 1Password CLI, never reads Keychain for bank secrets, never exports browser cookies.

Reject start requests whose param **keys** match:

```
^(.*_)?(password|passwd|secret|token|otp|mfa|sms|cookie|session|ssn|pan|account_number|routing)(s|_.*)?$
```

---

## 4. Architecture

Two roles, no always-on daemon in v1:

1. **CLI `private-desk`** — what Grok Bot runs on the **local computer** (user approves the command). Kick / get / cancel / doctor. Returns immediately on `start` (except tiny no-Holo demos may finish before return; still write a Job).
2. **Job worker** — forked by `start`, parent of Holo, writes `job.json`, exits when the job is terminal. Not a launchd daemon. Not Grok Bot’s tool-call process.

Lock: one Holo job at a time (the desktop is exclusive). If a worker already holds the lock, `start` **rejects** with `desktop_busy`. No queue in v1. Queue would be a scheduler and would start job B after the human left.

```
Grok Bot (cloud VM)  --kick / get-->  CLI on the Mac  --fork-->  worker  --child-->  holo
                                      job.json on disk <---------------------------'
```

Grok Bot’s **default computer is a cloud VM**. Routines keep running with the laptop closed. That machine is the **wrong** machine for Holo and must never open Chase. Local execution is Settings → General → Agent → Execution on Local Computer (default: ask every time).

v2 (parked): HTTP MCP, Tailscale/relay, inbound webhooks. Do not bind `0.0.0.0` silently. Do not install Holo’s MCP into Grok Bot as “local MCP” — that would attach to the cloud computer.

---

## 5. Grok Bot

**Skill / routine shape**

- The human speaks in plain language (`star the repo`). The Bot maps that to a kind id; they should not have to paste the CLI.
- Call `private-desk kinds` rather than guessing params
- Call `private-desk start …` with an idempotency key (`kind` + params + local date + a unique suffix). Same key within 24h returns the existing Job with `replayed: true` — tell them it already ran. A new ask (“do it again”) needs a new key.
- Tell the user the job id and that the laptop may be taken over
- Never pass secrets. Never read artifact files. Never start another job unless they ask
- On `needs_you`, copy `user_action.instruction` verbatim and stop. Do not ask them to paste codes into chat. When they confirm they finished on the laptop, `private-desk resume <id>` then `get`. Do not `start` again. `user_action.next` is `resume`.
- On success, report `kind` and `artifacts.artifact_dir` and stop
- On `desktop_busy`, say a job is running; they can wait or `private-desk cancel <id>` then start

**Cron / routines**

A scheduled routine runs in Grok Bot’s **cloud**, even if this Mac is asleep. It must **not** start Holo.

For kinds with `may_need_you: true`:

1. Routine posts: this job is due; are you at the laptop? 2FA/login may happen. Do not paste codes here.
2. Stop. If they never answer, skip the run.
3. On “yes” (Mac awake), kick `private-desk start` on the **local** computer.
4. Worker is detached. Chat timeout must not kill Holo.

Public demo kinds (dummy files, open-repo, star) are on-demand in chat. No cron required.

**Status**

v1 has no daemon → Grok Bot webhook. Grok Bot’s own “needs attention” / OS notifications cover the **preflight**. After kick, the user is at the laptop; the screen is the 2FA notification. `private-desk get` is for a still-open chat, not a substitute for “I walked away.”

Inbound “POST to a Grok Bot routine URL + sender key” is **not** a v1 dependency (undocumented / unstable). Parked.

---

## 6. Onboarding ladder

Agent-guided (AGENTS.md + `private-desk doctor`). Each step works if the next is not set up yet.

| Step | Kind | Holo? | Inference | Point |
| --- | --- | --- | --- | --- |
| 1 | `demo_dummy_files` | No | n/a | CLI, worker, Job, artifacts on disk |
| 2 | `demo_open_repo` | Yes | **hosted** (labeled) | Watch the desktop move; public URL |
| 3 | `demo_star_repo` (optional) | Yes | hosted (labeled) | Mutating encore; needs GitHub session |
| 4 | Session canary (template; bank instance is **private**) | Yes | **local** | Open the real site; human logs in if needed; confirm session; stop |
| 5 | Chase (private kind, not shipped) | Yes | **local** | Real job, only after 4 is green |

Holo **never types passwords**. Canary/login: navigate to the site; if logged out → `needs_you` / `needs_login`; human uses the real browser (1Password extension, Touch ID, SMS); resume; confirm “we’re in”; stop. That canary is success of the design.

`doctor` / agent prompt: for bank kinds, log into that site in the dedicated browser profile first. First run may be `needs_login` on purpose.

---

## 7. Kind pack

Kinds are YAML on disk. The assistant cannot create kinds. Shipping a new public demo is a PR. A bank is a **private** kind on the user’s machine.

**Public repo**

- `demo_dummy_files`, `demo_open_repo`, `demo_star_repo`
- Session-canary **template** (shape only: open URL → pause if login wall → confirm logged-in chrome → exit)
- README: how to add a private kind; local Holo required for anything with a real account

**Not in the public repo**

- Live Chase (or any bank) YAML, URLs as defaults, profile names that identify the author’s setup
- Screenshots, statements, real artifact dirs

Private kinds: `~/.config/private-desk/kinds/`. Public kinds: `kinds/` in the repo. Private wins on id clash.

`list_kinds` / `private-desk kinds` returns: `id`, `title`, `description`, `risk`, `inference`, `may_need_you`, `params` JSON Schema. **Never return the prompt.**

### Kind YAML (shape)

```yaml
id: demo_open_repo
title: Open the private-desk GitHub repo
description: Open the public repo in the browser and stop.
risk: read_only          # read_only | mutating
inference: hosted        # local | hosted | inherit
may_need_you: false
max_steps: 20
max_time_s: 180
url_allowlist:
  - https://github.com/
denied_actions:
  - transfer
  - pay
  - send_money
params:
  type: object
  additionalProperties: false
  properties: {}
launch_url: "{repo_url}"   # optional; macOS `open` this http(s) URL in {browser} before Holo
artifacts:
  dir_template: "{artifact_root}/{date}/{kind}"
prompt: |
  {browser} is being opened to {repo_url}.
  Confirm the repo page is visible. Do not hunt via Spotlight or Terminal.
  Do not log in. Do not star. Do not type passwords.
```

Bank / session-canary kinds: `inference: local`, `may_need_you: true`. v0 runners refuse `mutating` unless local config `allow_mutating = true`. Grok Bot still asks the user first. `demo_star_repo` is mutating.

The runner interpolates **only** validated params plus `artifact_dir`, `date`, `repo_url`, `browser`, `browser_profile`. Optional `launch_url` uses the same mapping; v0 opens it with macOS `open` / AppleScript before Holo. `launch_isolated: true` (public open-repo demo) starts a throwaway Chromium profile so the window lands on the current Space. Account kinds must leave this off. Missing required param → `kind_denied` before Holo.

`browser` is the menu-bar app name from local config (`private-desk setup --browser …`). If unset, prompts get `the default web browser`. Account kinds also interpolate `browser_profile`. Do not hardcode Chrome, Safari, or click coordinates in public kinds.

Dedicated **browser profile** (config `browser_profile`, often a Chrome profile named `private-desk`) is the default for account kinds: user’s cookies stay in that profile. Prompt: use `{browser}` + that profile, not a random window.

---

## 8. Job object

This is the only record CLI `--json` returns.

```json
{
  "protocol": "private-desk/v0",
  "job_id": "job_01JEXAMPLE",
  "kind": "demo_open_repo",
  "state": "running",
  "risk": "read_only",
  "inference": "hosted",
  "idempotency_key": "demo-open-repo-2026-08-27",
  "created_at": "2026-08-27T20:30:00Z",
  "updated_at": "2026-08-27T20:31:12Z",
  "started_at": "2026-08-27T20:30:05Z",
  "finished_at": null,
  "heartbeat_at": "2026-08-27T20:31:12Z",
  "step": {
    "id": "opening_browser",
    "label": "Opening the GitHub repo",
    "n": 2,
    "of": 8
  },
  "user_action": null,
  "summary": null,
  "error": null,
  "artifacts": null
}
```

### `state`

| state | meaning |
| --- | --- |
| `running` | Worker has the desktop (or is writing dummy files) |
| `needs_you` | Blocked on a human at the laptop |
| `succeeded` | Finished; artifacts on disk if any |
| `failed` | Terminal failure |
| `cancelled` | User or assistant cancelled |

v1 has no `queued` (reject when busy). Transitions: `running → {needs_you ⇄ running} → {succeeded, failed, cancelled}`. Never skip `needs_you` by stuffing an OTP into the API.

### `user_action` (only when `state=needs_you`)

```json
{
  "code": "mfa_required",
  "instruction": "Enter the code on your laptop. Do not send the code in chat.",
  "next": "resume"
}
```

`instruction` is for the human. The assistant copies it verbatim and stops. v1 then **waits for them to confirm** they finished on the laptop (no clickable modal yet). Then `private-desk resume <id>`. Do not start a new job. `next` is machine-readable (`resume`).

### `summary` / `artifacts` (only when `state=succeeded`)

v1 sets `artifacts` and leaves `summary` null. Do not clone the artifact list into `summary`.

```json
{
  "artifact_count": 3,
  "artifact_dir": "~/Finance/inbox/2026-08-27/chase-checking",
  "files": ["2026-07.pdf", "2026-08.pdf", "manifest.json"]
}
```

Filenames only. No parsed transactions. `manifest.json` is local-only; do not return its contents. v0 has **no** balances/totals.

### `error` (only when `state=failed`)

```json
{
  "code": "ui_changed",
  "message": "Chase statements page did not match the expected layout."
}
```

Stable `code` values (extend, don’t reuse):

| code | when |
| --- | --- |
| `mfa_required` | `needs_you`, not a terminal fail unless timeout |
| `session_expired` | logged out mid-job |
| `needs_login` | no usable browser session; human signs in on the laptop |
| `ui_changed` | layout guard fired |
| `unexpected_nav` | left URL allowlist |
| `timeout` | `max_time_s` or `max_steps` |
| `desktop_busy` | another job holds the desktop lock |
| `os_permission` | Screen Recording / Accessibility missing |
| `runtime_unavailable` | `holo` / runtime missing or unhealthy |
| `model_error` | inference backend failed |
| `kind_denied` | unknown kind, mutating disabled, or param validation |
| `guardrail` | runner tried a denied action |
| `bank_unavailable` | site down |
| `internal` | last resort; no stack traces |

`cancelled` is a state, not an error object.

---

## 9. CLI

Source of truth for Grok Bot. JSON on stdout when `--json` is passed; `--json` is default if stdout is not a TTY.

```
private-desk kinds
private-desk setup [--browser NAME] [--browser-profile NAME] [--repo-url URL]
private-desk start <kind> [--param key=value ...] [--idempotency-key k] [--wait]
private-desk get <job_id>
private-desk wait <job_id>       # laptop tty: poll until not running, then print get
private-desk status              # running + needs_you
private-desk cancel <job_id>
private-desk resume <job_id>     # human finished laptop action; waits until not needs_you
private-desk doctor              # runtime, permissions, inference, webhook N/A in v1
```

`start` returns immediately with the Job (`running`). Do not block until Holo exits. Dummy-files may be so fast the first `get` is already `succeeded`. Optional `--wait` (and `private-desk wait <id>`) is laptop-tty only: the worker still forks; this process polls until the Job leaves `running` (`needs_you`, `succeeded`, `failed`, `cancelled`) and prints `get`. `resume` writes the continue signal and waits until the Job leaves `needs_you` (`running` or terminal). It does not wait for Holo to finish.

Idempotency: if `idempotency_key` matches an in-flight or recently finished job (last 24h), return that Job with `replayed: true`; do not start a second Holo. A fresh start sets `replayed: false`. New human intent needs a new key.

Exit codes: `0` ok, `2` validation / `kind_denied`, `3` not found, `4` `desktop_busy`, `5` `runtime_unavailable` / `os_permission`, `1` everything else. Still print the JSON error body.

Successful start:

```json
{ "ok": true, "replayed": false, "job": { "job_id": "job_01JEXAMPLE", "state": "running" } }
```

Error:

```json
{
  "protocol": "private-desk/v0",
  "ok": false,
  "error": { "code": "kind_denied", "message": "Unknown kind 'sync_chase'." }
}
```

`doctor` must not print secrets. Report hosted vs local, whether llama.cpp is reachable, Holo binary, whether `browser` is set, whether `private-desk` is on PATH, and the **detected spawn parent** for Screen Recording (`hai-agent-runtime` plus Terminal/Cursor/iTerm/…). Missing Holo is a **warning** (dummy kinds still work); exit 0. `private-desk doctor --strict` exits 5 if Holo/permissions are not ready. Do not grep `holo doctor` English for permissions. `webhook: not used in v1`.

`private-desk setup` writes gitignored `config.toml`. Agents ask the human which browser app to use, then pass `--browser` (non-interactive). TTY with no flags walks the same three fields.

`private-desk logs` dumps worker.log only when stdout is a TTY. JSON never includes log text. Remote assistants must not call `logs`.

---

## 10. Worker and Holo

1. Create `~/.local/share/private-desk/jobs/<job_id>/`
2. Write `job.json` (public Job). Keep it the only API source of truth. Heartbeat `updated_at`.
3. Take desktop lock with `fcntl.flock` **before** writing `job.json`. If the lock is held → `desktop_busy` (no ghost job). The worker inherits the lock fd; the lock dies with the worker. No pid/mtime grace.
4. Materialize `artifact_dir` empty
5. If kind needs Holo: Python `holo_desktop.agent_client` (pause / resume / cancel). Do not treat `holo run` + wait-for-exit as the engine. Hosted: default runtime. Local: `SpawnConfig(base_url, model)`.
6. Stream events to laptop-only logs. Write a **redacted** copy. Never put Holo events in the Job. Detect `NEEDS_YOU: mfa_required|needs_login|os_permission` (or a pause event type), `pause()` the session, set `needs_you`.
7. **Pause:** 2FA / permission dialog / login wall. **No `submit_otp` API.** Resume when the human continues **on the laptop** (`private-desk resume <id>`). If the kind has `launch_url`, **reuse** the job browser window (do not open a second one), then `client.resume` (or a new session if Holo already `answer`ed). When the Job is terminal, close **only** that job browser (isolated profile), never the daily browser. Fake runner env is **tests only**.
8. On success, confirm expected artifacts exist before `succeeded`. If Holo claims done and the dir is empty (for kinds that require files), `failed` / `internal`
9. Kill Holo on `cancel`, `timeout`, `unexpected_nav`, `denied_actions`
10. Release lock; worker exits

HoloDesktop (as of 2026): embed with `holo_desktop.agent_client` (`pause` / `resume` / `cancel`). CLI `holo run` is not the worker engine. First run downloads closed-source `hai-agent-runtime`. macOS: Screen Recording + Accessibility. Linux: X11, not Wayland. `doctor` runs `holo doctor` when present but does not grep its English output.

Do not implement a “give the assistant a live view” debug flag. Local only: `private-desk logs <id>` to the tty of the person at the laptop.

---

## 11. Inference

Local default for anything sensitive: **llama.cpp** `llama-server` as documented by H Company for Mac (not bundled inside Holo). Example:

- Model: `Hcompany/Holo-3.1-35B-A3B-GGUF`
- URL: `http://127.0.0.1:8080/v1`

`private-desk` stores `holo_base_url` + `holo_model`. Any OpenAI-compatible server (LM Studio, etc.) is valid if pointed there. Docs: llama.cpp is the known-good path.

Holo 3.1 Q4 is ~21 GB weights; M3+/Max with enough unified memory (author: M4 Max). Holo 3 122B is hosted-only; do not use it for banks.

Suggested config (`~/.config/private-desk/config.toml`, never committed):

```toml
inference = "local"                 # default for kinds with inherit
holo_bin = "holo"
holo_base_url = "http://127.0.0.1:8080/v1"
holo_model = "holo3-1-35b"
artifact_root = "~/Finance/inbox"
repo_url = "https://github.com/<user>/private-desk"
browser = "Google Chrome"           # menu-bar app name; from `private-desk setup`
browser_profile = "private-desk"    # dedicated profile in that browser
allow_mutating = false
```

Hosted inference: `holo login` / Models API. `list_kinds` must show `inference` so the assistant can warn. Bank and account-canary kinds ignore install default and require local.

v1 does **not** auto-start llama.cpp. `doctor` checks the URL if local kinds exist.

---

## 12. Test plan

- Unit: redaction strips a fake Holo payload (screenshot b64, `$12,345.67`, account number)
- Unit: start rejects params `{ "password": "x" }`
- Unit: unknown kind → `kind_denied`
- Unit: idempotency returns the same `job_id`
- Unit: second start while lock held → `desktop_busy`
- Integration: fake runner (no Holo) `running → succeeded` with dummy files
- Integration: fake runner pauses at login → `needs_you` → `resume` → `succeeded`
- Integration: cancel during running (worker + child die; lock released)
- Manual: `private-desk doctor --strict` on a machine without Accessibility; expect non-zero only in strict mode
- Manual: `demo_dummy_files` then `demo_open_repo` via CLI
- Manual: Grok Bot local command kick of dummy files (no bank)

Do not automate a real bank login in CI. Do not put Chase kinds in CI.

---

## 13. Repo layout

```
private-desk/
  README.md
  SPEC.md              # this file
  LICENSE              # Apache-2.0
  AGENTS.md            # onboarding for a code agent / Grok Bot skill gist
  pyproject.toml
  src/private_desk/
    cli.py
    worker.py          # lock, job.json, fork, Holo wrap
    jobs.py            # state machine + json store
    redact.py
    kinds.py
    doctor.py
  kinds/
    demo_dummy_files.yaml
    demo_open_repo.yaml
    demo_star_repo.yaml
    _session_canary.template.yaml
  tests/
```

v1 ship bar: CLI + worker + public demo kinds + doctor + AGENTS.md. Chase is a private kind you add later, local llama.cpp, after session canary.

---

## 14. Parked / later

- Always-on daemon, job queue (only with re-confirm of `may_need_you` on dequeue)
- Grok Bot inbound webhook
- Remote MCP / NAT relay
- llama.cpp started by our worker
- 1Password / cookie export
- Opt-in `aggregates` (balances) gated by kind + user flag; default off
- Mutating kinds beyond optional star
- Native Holo “background mode” if it changes the one-job lock

---

## 15. Decisions (signed off)

| Topic | Decision |
| --- | --- |
| Product / CLI | `private-desk` |
| License | Apache-2.0 |
| Language | Python |
| Engine | HoloDesktop; assistant never sees Holo tools |
| Process | Job worker, detached; no daemon in v1 |
| Busy desktop | Reject (`desktop_busy`), no queue |
| Grok Bot cron | Ask first; never auto-start `may_need_you` |
| Status poke | No webhook in v1 |
| Inference | llama.cpp default for local; hosted OK for public demos only |
| Sessions | Real browser profile; no stolen cookies / 1Password API |
| Login | Human on the laptop; Holo never types passwords |
| Onboarding | Dummy → open repo → optional star → session canary → Chase |
| Public repo | Demos + template; bank YAML private |
| 2FA | `needs_you` + `resume`; no OTP in the API |
