# First-time onboard

**Humans:** this is the paste block for a code agent on a new Mac. Product law: [SPEC.md](SPEC.md). After PATH works, kick jobs from Grok Bot (local computer), not from Cursor.

**Agents:** you are onboarding this Mac. You are not changing the product unless they ask. Read [SPEC.md](SPEC.md), [AGENTS.md](AGENTS.md), and [README.md](README.md) first. Walk **gates**. Stop when a step is not set up. Run `private-desk doctor` after each install. Use `onboarding.next` from doctor JSON — do not treat a non-strict doctor as a hard fail.

---

## Paste this into Cursor / Codex / your repo agent

```
You are onboarding private-desk on this Mac. The human talks in plain language. You run local commands. You do not start Chase or any private bank kind unless they already added one and asked.

Law: SPEC.md + AGENTS.md. Humans: README.md. This prompt is the first-time ladder, not a license to revive daemons, webhooks, MCP queues, or PYTHONPATH=src.

## Goal
A working Job on this laptop, then the same kick from Grok Bot. Dummy files prove the control plane. Open/star (optional X) prove hosted Holo. Dino proves Jev (no screens). Stop at the first missing layer.

## Hard rules
- Every kick is local-computer CLI. Grok Bot’s default computer is a cloud VM — that machine must never run Holo or dino.
- If `private-desk` is not on PATH, stop. Put clone `.venv/bin` on PATH in BOTH ~/.zprofile AND ~/.zshrc. Do not set PYTHONPATH=src.
- `start` forks a worker and returns. Do not pass --wait from a Bot. New ask → new idempotency key (KIND-YYYY-MM-DD-<unique>).
- may_need_you: ask “are you at the laptop?” If no, do not start. On needs_you, paste user_action.instruction verbatim. No codes in chat. Then resume, not start.
- Never print AI_GATEWAY_API_KEY / typesafe_api_key. Never private-desk logs from a remote assistant. Never --param password=…
- Do not install Holo MCP into Grok Bot (`holo install` into Grok). Do not bind 0.0.0.0. Do not invent tweet text.
- Do not start demo_dino from Cursor. Watch the throwaway Chromium window. Sequoia App Management ≠ Full Disk Access.
- doctor without --strict is not a hard fail. Missing Holo → dummy only.
- pytest is for people changing the repo, not required to see a job.
- Do not download local llama.cpp weights on minute one.

## Gates (stop when blocked)
0. Clone + venv
   git clone https://github.com/jachian22/private-desk && cd private-desk
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   Put `$PWD/.venv/bin` on PATH in ~/.zprofile and ~/.zshrc. Open a new Terminal. `which private-desk` must work without cd.
   private-desk doctor
   private-desk setup --browser "<menu-bar name they use>"   # Google Chrome, Firefox, Safari, …

1. dummy — no Holo
   Prove CLI / worker / Job. Prefer the human saying “dummy files” in Grok Bot once PATH + skill (below) work. Until then, CLI is ok:
   private-desk start demo_dummy_files --idempotency-key dummy-$(date +%F)
   Then get. Report kind + artifact_dir. Do not read the files.

2. Holo (only if they want the desktop to move)
   Consumer install: curl -fsSL https://install.hcompany.ai/install.sh | bash
   Then: holo login
   First run downloads closed-source hai-agent-runtime (H Company’s, sha256-verified). Do not vendor it.
   macOS: Screen Recording + Accessibility for hai-agent-runtime AND the app that ran private-desk (doctor.checks.spawn_parent).
   Do NOT `holo install` / Holo MCP into Grok Bot.
   Before demo_open_repo: hosted Holo, public GitHub page, screens go to H Company, laptop will be taken over. Ask. Then start from the Bot if PATH works.
   Star is optional: GitHub already logged in in {browser}, allow_mutating = true, ask first. Do not auto-chain after open.
   X is optional: daily browser, canned --param message= from kinds, ask first. Do not invent a tweet.

3. dino — not Holo
   pip install -e ".[dino]"
   Jev: npx vercel ai-gateway setup (Keychain) or AI_GATEWAY_API_KEY. Never print it. Gateway ZDR 403s Jev — do not turn ZDR on for this demo.
   Chromium only (Safari/Firefox fail). Ask first. Takes the keyboard in a throwaway profile.
   Sequoia: App Management for the app that will spawn that Chrome (Grok’s local runner or Terminal — not Cursor, not Full Disk Access).
   Start from Grok Bot: “chrome dino”. Watch the window. Leftover dino windows: they close; next start kills that profile.

4. Later (do not start here): session canary template → private kinds in ~/.config/private-desk/kinds/ → local llama.cpp on 127.0.0.1 only.

## After PATH works — Grok Bot skill
Paste this into the Bot. Replace CLI with `which private-desk` on THIS Mac.

You kick private-desk on this Mac (local computer only). The human never pastes the CLI.
CLI: /ABS/PATH/TO/private-desk/.venv/bin/private-desk
Grok Settings → Agent → Execution on Local Computer (not the cloud VM).
dummy files → demo_dummy_files
open the repo → demo_open_repo (hosted; screens go to H Company; ask first)
star the repo → demo_star_repo (same hosted note; ask; allow_mutating)
tweet / post to x → demo_post_x (ask; allow_mutating; canned message enum only; never auto-chain)
chrome dino → demo_dino (NOT Holo; Jev numbers; Chromium; ask; throwaway window; App Management; do not start from Cursor)
Else: private-desk decide --utterance "…" — talk if ask_first/blocked_by; decide never starts.
Never cron/routine start. New key per ask. No --wait. get until terminal.
needs_you: paste instruction, stop, resume later. succeeded: kind + artifact_dir (dino: they watched the window). Do not read files.

## If stuck
desktop_busy: wait or cancel. replayed: true → already ran; new ask needs a new key.
```

---

## Known friction

These are real. The starter prompt above already stops on them; this list is for humans and agents who hit one mid-ladder.

| Friction | What happens | What to do |
| --- | --- | --- |
| `private-desk` not found | Grok’s login shell has no PATH | `.venv/bin` in **both** `~/.zprofile` and `~/.zshrc`. New Terminal. Never `PYTHONPATH=src`. |
| Skill `CLI:` is someone else’s path | Bot runs a missing binary | `which private-desk` on **this** Mac; paste that path. |
| Grok still on cloud VM | Dummy “works” on a machine with no desktop | Settings → Agent → Execution on **Local Computer**. |
| `doctor` missing Holo, exit 0 | Agent treats it as fatal | Dummy still works. `--strict` is later. Use `onboarding.next`. |
| Hosted open/star/X | Screens go to H Company | Say so **before** start. Public pages only. |
| Screen Recording / Accessibility | Holo cannot drive the Mac | Grant to `hai-agent-runtime` **and** `doctor.checks.spawn_parent`. |
| Sequoia App Management vs FDA | Dino cannot launch/quit throwaway Chrome | App Management for the spawn parent. **Not** Full Disk Access. |
| Dino from Cursor | Wrong parent; keyboard stolen in the IDE | Kick from Grok Bot / Terminal. Human watches the throwaway window. |
| Safari/Firefox as `{browser}` | `demo_dino` is Chromium loopback CDP | Setup Chrome (or another Chromium). Other browsers still fine for Holo demos. |
| Gateway ZDR | Jev 403 | Do not enable Zero Data Retention on the Gateway key used for dino. Never print the key. |
| `allow_mutating` still false | star / X denied | Consent in `config.toml`. Do not silently flip it. Do not auto-chain star after open. |
| Tweet text invented | Spec violation | Canned `message` enum from `kinds` only. |
| `holo install` into Grok | Holo MCP on the Bot | Do not. private-desk kicks; Holo stays behind the worker. |
| `needs_you` + codes in chat | Trust boundary | Paste `instruction` verbatim. Human finishes on the laptop. `resume`. |
| `desktop_busy` | One desktop job at a time | Wait or `cancel`. No queue. |
| Same idempotency key | `replayed: true` | New ask → new key. |
| Leftover dino Chrome | Throwaway profile left up | Human closes it. Next `demo_dino` start kills that profile first. |
| Local llama / bank on day one | 20GB+ detour | After hosted demos feel real. Bind `127.0.0.1` only. |
| `private-desk logs` from the Bot | Leaks worker log | Laptop tty only. |

`private-desk doctor` JSON includes `onboarding.next`, `onboarding.ready`, and `onboarding.blocked` so an agent can stop without guessing.
