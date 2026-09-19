# AGENTS.md

This file is for **coding agents** (Cursor, Codex, a forker’s agent).

- **First-time Mac:** [STARTER.md](STARTER.md) (paste-in onboarder + known friction).
- **Humans:** [README.md](README.md). Product law: [SPEC.md](SPEC.md).
- **A** — you are changing this repo. **B** — they already cloned; walk the ladder. **Skill** — runtime kicks on an installed CLI.

There is no screenshot, click, type, or `holo run` tool for Grok Bot. The assistant kicks `private-desk` on the **user’s Mac**. Holo stays behind the worker.

---

## A. You are building or changing this repo

1. Read `SPEC.md` before coding. Do not revive the old daemon/webhook/MCP/queue design.
2. The assistant-visible object is the **Job**. Redact everything from Holo. Never return prompts, logs, PDFs, or screenshots.
3. `start` forks a **job worker** and returns. Do not make Grok Bot the parent of Holo. No always-on daemon in v1.
4. Busy desktop → **reject** (`desktop_busy`). No queue.
5. No `submit_otp`. No password/cookie/1Password APIs. Holo never types passwords.
6. Public kinds only: dummy files, open-repo, optional star, canned X post, chrome dino, session-canary **template**. Bank YAML stays in `~/.config/private-desk/kinds/` (gitignored private dir, not this repo).
7. `demo_star_repo` and `demo_post_x` are mutating: require `allow_mutating = true` in config. Do not invent tweet text; use the canned `message` enum.
8. Bank / session-canary kinds: `inference: local` only. Hosted Holo is OK for public demos and must stay labeled.
9. Do not bind `0.0.0.0`. Do not install Holo MCP into Grok Bot.
10. Tests: `pytest`. Do not hit real banks in CI. Use `PRIVATE_DESK_HOME` so tests never touch the developer’s real config.
11. `decide` labels a gate. It never starts a job. Never print `typesafe_api_key` or `AI_GATEWAY_API_KEY`. Formulaic `start` does not need Jev. `npx vercel ai-gateway setup` Keychain is a valid Jev key source.

Local workstream briefs stay in gitignored `plans/`. Product law is SPEC.md + AGENTS.md.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

---

## B. You are onboarding a human who cloned this (or Grok Bot on their Mac)

Walk the ladder. Stop when a step is not set up yet. Do not invent Holo prompts. Do not start Chase or any private bank kind unless they already added one and asked.

**Every kick is local-computer CLI**, not Grok Bot’s cloud VM. If `private-desk` is not on PATH, stop — do not set `PYTHONPATH=src`.

```bash
private-desk doctor
private-desk setup --browser "Google Chrome"   # menu-bar name; Firefox/Safari/etc. also fine
private-desk start demo_dummy_files --idempotency-key dummy-$(date +%F)
private-desk get <job_id>   # or: private-desk start … --wait  (prints get when it leaves running)
```

| Step | Command | Needs | Inference |
| --- | --- | --- | --- |
| 1 | `start demo_dummy_files` | nothing | n/a |
| 2 | `start demo_open_repo` | Holo + Screen Recording + Accessibility; laptop will be taken over; `{browser}` from setup | **hosted** (screens go to H Company; OK, public page) |
| 3 | `start demo_star_repo` | step 2 + GitHub login in `{browser}` + `allow_mutating = true` | hosted |
| 3b | `start demo_post_x --param message=…` | at the laptop; daily `{browser}` logged into X; `allow_mutating = true`; canned enum only | hosted (everyday X window) |
| 3c | `start demo_dino` | at the laptop; Chromium; Jev via `AI_GATEWAY_API_KEY`, `npx vercel ai-gateway setup`, or TypeSafe; **not Holo**; takes the keyboard in a throwaway profile; Sequoia: App Management for Terminal (the app that ran `private-desk`) so we can launch/quit that Chrome — not Full Disk Access | Jev Nouls (Runner numbers, not screens) |
| 4 | private session canary | local llama.cpp + logged-in site in `{browser}` profile `{browser_profile}` | **local** |
| 5 | private bank kind | step 4 green | **local** |

If `doctor` says Holo is missing, do **step 1 only**. Dummy files still work. Do not run step 2 until they install Holo. `doctor` without `--strict` must not be treated as a hard fail.

If a kind has `may_need_you: true` (or you are about to start a bank job): **ask first** — are they at the laptop? 2FA/login may happen. Do not paste codes in chat. If they do not confirm, do not start.

On `needs_you`, paste `user_action.instruction` verbatim and stop. When they confirm they finished on the laptop, `private-desk resume <id>` then `get`. Do not `start` again.

On `succeeded`, report `kind` and `artifacts.artifact_dir`. Do not read the files.

On `desktop_busy`: a job is running. They can wait or `private-desk cancel <id>`.

Never pass `--param password=…` or any secret. Never call `private-desk logs` from a remote assistant (laptop tty only).

Cron/routines: **message**, do not start Holo. Start only after they say they are at the laptop.

---

## Grok Bot skill (copy into the Bot)

Humans talk in plain language. The Bot runs the CLI on the **local computer**. Forkers: generate this from [STARTER.md](STARTER.md) after `which private-desk` — the `CLI:` line below is this author’s Mac.

```
You kick private-desk on this Mac (local computer only). The human never pastes the CLI.

CLI: /Users/jachian/Documents/dev/private-desk/.venv/bin/private-desk

They might say:
- dummy files / dummy → demo_dummy_files
- open the repo → demo_open_repo (hosted: screenshots go to H Company; laptop may be taken over)
- star the repo → demo_star_repo (same hosted note; ask if they are at the laptop first)
- tweet / post to x / get the word out → demo_post_x (hosted, daily browser; ask first; allow_mutating; pass --param message= the sole enum from kinds; new key; never auto-chain after star)
- chrome dino / dinosaur → demo_dino (NOT Holo; Jev sees Runner numbers; code taps keys; Chromium; ask first; takes the keyboard in a throwaway window; new key; macOS App Management for Terminal if it asks; watch that window — do not start from Cursor)

If it is not one of those, run: private-desk decide --utterance "<their words>"
If decide says ask_first or blocked_by, talk. Do not start.
If legal and next=start, start that kind with a new idempotency key.
Never start from a cron/routine, even if decide says start.
decide never starts a job. Do not pass --apply (there is none).

start KIND --idempotency-key KIND-YYYY-MM-DD-<unique>
A new ask needs a new key. replayed: true means it already ran.
Do not pass --wait. After start, get until the job is succeeded, failed, cancelled, or needs_you.

needs_you: paste user_action.instruction and stop. When they say they finished on the laptop, resume then get. Do not call decide for resume.
succeeded: kind and artifact_dir. For demo_dino also say it finished (they watched the throwaway window). Do not read the files.
desktop_busy: a job is already running.
```
