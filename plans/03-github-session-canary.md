# Stream 3 — GitHub session canary (private, local)

**Use this file as the entire brief for a dedicated chat.**  
Depends on stream 1 (Holo moves the desktop; pause/`needs_you` trusted) and stream 2 (llama.cpp pet reachable). Do not implement Chase statement download here.

**Start prompt for a new session:**

> Read `plans/03-github-session-canary.md`, `SPEC.md`, and `AGENTS.md`. Execute stream 3 only. Private kind YAML stays in `~/.config/private-desk/kinds/`. Never commit it. First local canary is GitHub, not Chase. llama.cpp is a pet — if it is down, tell me to start it; do not spawn it. Holo must never type passwords.

---

## Goal

Prove **session reuse** on a real logged-in site, with **local** inference, in the dedicated Chrome profile, without pulling bank PDFs.

**Done when**

- Chrome profile named `private-desk` exists (human-created).
- Private kind `session_canary_github` (name flexible) is in `~/.config/private-desk/kinds/` only.
- `inference: local`, `may_need_you: true`, `runner: holo`.
- Logged-**out** run: `needs_you` / `needs_login` (token **or** quiet pause). Human signs in on the laptop (1Password in the browser is fine). `resume`. Confirm signed-in GitHub chrome. **Stop. No star required.**
- Logged-**in** rerun: succeed without `needs_you` (or brief no-op).
- Job JSON never contains cookies, HTML, or screenshots.
- Kind does **not** appear as a public demo in git.

**Not done:** Chase statements, 1Password CLI, cookie export, hosted inference for this kind.

---

## Locked decisions (do not reopen)

| Topic | Decision |
| --- | --- |
| Site | **GitHub**, not Chase. Chase home/statements = stream 4 |
| Browser | Dedicated Chrome profile `private-desk` from config `browser_profile`. Not the default browser (that’s stream 1 demos) |
| Inference | **local only.** Hosted is a spec violation |
| Login | Human on the laptop. Holo never types passwords |
| Quiet pause | Still `needs_you` |
| Pet | If llama-server is down, refuse start with boot instructions (stream 2 UX) |
| Public repo | Template only: `kinds/_session_canary.template.yaml`. Live YAML is gitignored (`kinds/private/`, `~/.config/...`) |

---

## Current code (as of this plan)

- Template: `kinds/_session_canary.template.yaml` (skipped by loader because `_` prefix). Copy to private dir, change `id`, `url_allowlist`.
- Private kinds dir: `~/.config/private-desk/kinds/` (see `paths.private_kinds_dir()`). Private **wins** on id clash.
- Prompt already says use `browser_profile` and emit `NEEDS_YOU:`.
- Holo opening a **named Chrome profile** is not a first-class API — the kind **prompt** must say how (e.g. open Chrome, Profile menu, `private-desk`). If live Holo uses the wrong profile, tighten the prompt; do not scrape Chrome’s user-data-dir from our code in v1 unless stream 1 proved a reliable flag.

---

## Slices

### 3a — Human: Chrome profile

1. Chrome → add profile named `private-desk` (or match `browser_profile` in config).
2. Do not use this profile as daily Gmail if you can avoid it.
3. Optional: log into GitHub here **before** the first canary (then 3c logged-in path is first). Logged-out first is a better test of `needs_you`.

### 3b — Private kind file

Copy template → `~/.config/private-desk/kinds/session_canary_github.yaml`.

Must set:

- `id: session_canary_github` (or similar)
- `inference: local`
- `may_need_you: true`
- `url_allowlist:` GitHub hosts only (`https://github.com/`, `https://github.com/login`, etc. as needed)
- `denied_actions:` include star if you want canary read-only; or allow viewing only
- Prompt: default **Chrome profile `private-desk`**, go to github.com, pause on login/2FA, never type secrets, confirm signed-in avatar/dashboard, **exit**. Do not star (star is public demo in default browser).

`private-desk kinds` must list it and **must not** return `prompt`.

### 3c — Logged-out canary (laptop)

1. Confirm pet: `doctor` local_model reachable. If not, tell human to start llama-server; do not spawn.
2. Ask: at the laptop? 2FA/login may happen. Do not paste codes in chat.
3. `start session_canary_github --idempotency-key gh-canary-out-$(date +%F)`
4. Expect `needs_you`. Copy `user_action.instruction`. Stop.
5. Human logs in in that Chrome profile.
6. `resume`
7. Succeed when signed-in GitHub is visible. No artifacts required.

**Stop the line** if Holo types into the password box.

### 3d — Logged-in rerun

Same kind, new idempotency key. Should not need login. If it does, session didn’t stick in that profile — fix prompt/profile, don’t steal cookies.

---

## Files you may touch

- `~/.config/private-desk/kinds/*.yaml` — **not git**
- `kinds/_session_canary.template.yaml` — only if the template is wrong for GitHub-shaped canaries (keep example.com or document GitHub as the author’s first canary without putting their login URLs as the runnable public id)
- `src/private_desk/holo_session.py` / prompts — if Holo ignores profile
- README: “copy template to config kinds; first canary we recommend is GitHub, local only”
- **Never** commit the live canary YAML
- **Never** Chase URLs in this stream

---

## Human checklist

- [ ] llama-server running (pet)
- [ ] Stream 1 Holo/permissions already work
- [ ] At the laptop for 3c
- [ ] Chrome profile `private-desk` created
- [ ] Will sign in on the laptop, not in chat

---

## Stop / escalate

- Hosted inference “to save time”
- 1Password CLI / cookie export
- Starring from this profile as the canary success condition (optional later; not done-when)
- Chase statements
- Putting the private YAML in `kinds/` in git
