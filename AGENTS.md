# AGENTS.md

This file is for **coding agents** (Cursor, Codex, a forker’s agent). Humans: [README.md](README.md). Product law: [SPEC.md](SPEC.md).

There is no screenshot, click, type, or `holo run` tool for Grok Bot. The assistant kicks `private-desk` on the **user’s Mac**. Holo stays behind the worker.

---

## A. You are building or changing this repo

1. Read `SPEC.md` before coding. Do not revive the old daemon/webhook/MCP/queue design.
2. The assistant-visible object is the **Job**. Redact everything from Holo. Never return prompts, logs, PDFs, or screenshots.
3. `start` forks a **job worker** and returns. Do not make Grok Bot the parent of Holo. No always-on daemon in v1.
4. Busy desktop → **reject** (`desktop_busy`). No queue.
5. No `submit_otp`. No password/cookie/1Password APIs. Holo never types passwords.
6. Public kinds only: dummy files, open-repo, optional star, session-canary **template**. Bank YAML stays in `~/.config/private-desk/kinds/` (gitignored private dir, not this repo).
7. `demo_star_repo` is mutating: require `allow_mutating = true` in config.
8. Bank / session-canary kinds: `inference: local` only. Hosted Holo is OK for public demos and must stay labeled.
9. Do not bind `0.0.0.0`. Do not install Holo MCP into Grok Bot.
10. Tests: `pytest`. Do not hit real banks in CI. Use `PRIVATE_DESK_HOME` so tests never touch the developer’s real config.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

---

## B. You are onboarding a human who cloned this (or Grok Bot on their Mac)

Walk the ladder. Stop when a step is not set up yet. Do not invent Holo prompts. Do not start Chase or any private bank kind unless they already added one and asked.

**Every kick is local-computer CLI**, not Grok Bot’s cloud VM.

```bash
private-desk doctor
private-desk start demo_dummy_files --idempotency-key dummy-$(date +%F)
private-desk get <job_id>
```

| Step | Command | Needs | Inference |
| --- | --- | --- | --- |
| 1 | `start demo_dummy_files` | nothing | n/a |
| 2 | `start demo_open_repo` | Holo + Screen Recording + Accessibility; laptop will be taken over | **hosted** (screens go to H Company; OK, public page) |
| 3 | `start demo_star_repo` | step 2 + GitHub login in the browser + `allow_mutating = true` | hosted |
| 4 | private session canary | local llama.cpp + logged-in site in the `private-desk` Chrome profile | **local** |
| 5 | private bank kind | step 4 green | **local** |

If `doctor` says Holo is missing, do **step 1 only**. Dummy files still work. Do not run step 2 until they install Holo. `doctor` without `--strict` must not be treated as a hard fail.

If a kind has `may_need_you: true` (or you are about to start a bank job): **ask first** — are they at the laptop? 2FA/login may happen. Do not paste codes in chat. If they do not confirm, do not start.

On `needs_you`, paste `user_action.instruction` verbatim and stop.

On `succeeded`, report `kind` and `artifacts.artifact_dir`. Do not read the files.

On `desktop_busy`: a job is running. They can wait or `private-desk cancel <id>`.

Never pass `--param password=…` or any secret. Never call `private-desk logs` from a remote assistant (laptop tty only).

Cron/routines: **message**, do not start Holo. Start only after they say they are at the laptop.

---

## Grok Bot skill (copy into the Bot)

```
You dispatch private-desk on the user's Mac. You never see the desktop.

1. private-desk kinds — then start with kind + params + idempotency key (kind-params-local-date).
2. Tell them the job id and that the laptop may be taken over.
3. Hosted inference kinds: warn that screenshots go to H Company. Bank/canary kinds must be local.
4. may_need_you or bank: ask "are you at the laptop?" before start. Cron must not auto-start.
5. needs_you: copy user_action.instruction. Do not ask for the code in chat.
6. succeeded: kind + artifact_dir. Do not read files. Do not start another job unless they ask.
7. desktop_busy: wait or cancel. Never queue by retry-spamming start.
8. Never pass secrets. Never use Holo MCP. Never run this on the cloud computer.
9. Never call private-desk logs. That is laptop tty only.
```
