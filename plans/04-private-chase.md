# Stream 4 — Private Chase kind

**Use this file as the entire brief for a dedicated chat.**  
Hard gate: stream 3 GitHub canary is **green** (local inference, dedicated Chrome profile, human login, no password typing by Holo). If 3 is not green, stop and send the human back.

**Start prompt for a new session:**

> Read `plans/04-private-chase.md`, `SPEC.md`, and `AGENTS.md`. Execute stream 4 only. Chase YAML is private (`~/.config/private-desk/kinds/`). Never commit it. Never hit Chase in CI. Local llama.cpp pet must be up — do not spawn it. Ask if I am at the laptop before start. Holo never types passwords or OTPs. Do not read statement PDFs.

---

## Goal

On **this** Mac, download Chase statement PDFs into a local artifact dir. Grok Bot / the assistant sees only Job JSON (kind, state, filenames, `artifact_dir`). Screens never leave the machine (local Holo).

**Done when**

- Private kind exists only under `~/.config/private-desk/kinds/` (e.g. `sync_chase_statements.yaml`).
- `inference: local`, `risk: read_only`, `may_need_you: true`.
- Params schema: at least `product` + `period` (enums; `additionalProperties: false`).
- URL allowlist = Chase hosts only. `denied_actions` includes transfer, pay, send_money, wire, zelle, submit_payment.
- Live run at the laptop: 2FA → `needs_you` (token or quiet pause) → human on laptop → `resume` → PDFs on disk → Job `succeeded` with **filenames only**.
- Mutating stays off. No balances in the Job.
- Cancel mid-run releases the desktop lock. Failures use spec `error.code` (`ui_changed`, `session_expired`, `timeout`, `needs_login`, …).

**Not done:** public Chase YAML, hosted Holo, moving money, aggregates/balances, webhook, daemon.

---

## Locked decisions (do not reopen)

| Topic | Decision |
| --- | --- |
| Public git | **No** live Chase kind. Template/shape in repo only if generic |
| Inference | **local**. Hosted = H Company sees the bank. Forbidden |
| Browser | Chrome profile `private-desk` (same as stream 3). Session reuse; no cookie export |
| Login / 2FA | Human on the laptop. No OTP in chat or API |
| Quiet pause | Still `needs_you` |
| Pet | llama-server must already be running |
| Grok Bot | Ask “at the laptop?” before start. Cron **messages** only, never auto-starts |
| Artifacts | Paths + filenames. Do not read PDF contents in chat |
| Busy desktop | Reject `desktop_busy`; no queue |

---

## Current code (as of this plan)

- No Chase file in git (correct).
- Kind loader: private dir overlays public ids.
- Worker: flock, `holo_session`, redaction, `resume.signal`.
- Dummy PDFs are the artifact *shape* to copy (manifest local-only; don’t return contents).
- `requires_artifacts: true` for this kind so empty dir after “success” → `failed` / `internal`.

---

## Slices

### 4a — Private YAML (authoring, not CI)

Create `~/.config/private-desk/kinds/sync_chase_statements.yaml`.

Suggested shape (adapt URLs to what Chase actually uses; keep allowlist tight):

- `id: sync_chase_statements`
- `params.required: [product, period]`
- `product` enum: `checking`, `savings`, `credit` (drop any you don’t have)
- `period` enum: `last_statement`, `last_3_statements`
- `dir_template: "{artifact_root}/{date}/{kind}-{product}"` — need interpolation of **validated params** in `dir_template` if not already (`kinds.py` / `artifact_dir_for` today formats `artifact_root`, `date`, `kind` only). **If product is missing from the path, add `**params` to the format mapping** in this stream.
- Prompt: existing profile only; statements for `{product}` / `{period}`; save PDFs to `{artifact_dir}`; do not open transfer/Zelle/pay; on 2FA emit `NEEDS_YOU: mfa_required` and wait; never type secrets.

`private-desk kinds` shows schema, not prompt.

### 4b — Preflight

1. llama-server up (stream 2 UX if not).
2. Human at laptop.
3. Chrome profile already logged into Chase **or** accept first run as `needs_login` (same as canary).
4. Hosted inference must not be used even if pet is down.

### 4c — Live statement run

```bash
private-desk start sync_chase_statements \
  --param product=checking \
  --param period=last_statement \
  --idempotency-key chase-checking-$(date +%F)
```

Laptop will be taken over. On `needs_you`, copy instruction; human completes 2FA on the Mac; `resume`.

Success: PDFs in artifact_dir (default `~/.local/share/private-desk/inbox/...` or `artifact_root` from config, e.g. `~/Finance/inbox`). Job lists filenames. **Do not open/read them in the assistant.**

### 4d — Failure / cancel

Exercise or at least handle:

- `cancel` while running → lock released, Holo stopped
- Timeout → `timeout`
- Logged out mid-job → `session_expired` / `needs_login` if we can classify without OCR dumps in the Job
- Wrong page → `ui_changed` if we add a guard; don’t put page text in `error.message`

No pytest against real Chase. Optional: fake runner sequences already exist; don’t add bank fixtures with real layouts.

---

## Files you may touch

- `~/.config/private-desk/kinds/sync_chase_statements.yaml` — **never git**
- `src/private_desk/runners.py` `artifact_dir_for` — interpolate validated params if needed
- `README.md` — “add a private bank kind; never commit it; local only”
- Guardrails in the **kind prompt** + allowlist; do not build a payment API
- **Never** commit statements, screenshots, or Chase YAML
- **Never** `private-desk logs` from a remote assistant

---

## Human checklist

- [ ] Stream 3 green
- [ ] llama-server running
- [ ] At the laptop; 2FA device nearby
- [ ] Chase login in `private-desk` Chrome profile (or willing to sign in when asked)
- [ ] OK with Holo seeing Chase **on device** (local model + closed-source runtime)

---

## Stop / escalate

- Hosted Holo for Chase
- Anything that moves money
- Pasting OTPs or passwords into chat
- Reading statement PDFs to “summarize”
- Publishing the kind in this repo
- CI hitting chase.com
