# private-desk

Privacy-preserving desktop jobs for a consumer assistant (Grok Bot first), powered by [HoloDesktop](https://github.com/hcompai/holo-desktop-cli). The assistant **kicks** a job on your laptop and never sees the screen.

Law: [SPEC.md](SPEC.md). Agents: [AGENTS.md](AGENTS.md). License: [Apache-2.0](LICENSE).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# optional: Jev/decide live calls
# pip install -e ".[jev]"
```

Put `.venv/bin` on PATH in **both** `~/.zprofile` and `~/.zshrc` so login shells and Grok’s local computer can run `private-desk` without `cd` or `PYTHONPATH=src`:

```bash
# use your clone path
export PATH="/ABS/PATH/TO/private-desk/.venv/bin:$PATH"
```

Then:

```bash
private-desk doctor
private-desk setup --browser "Google Chrome"   # or Safari, Firefox, … — menu-bar name
```

If `private-desk` is not found, stop and fix PATH. Do not set `PYTHONPATH=src`.

### Starter prompt (paste into Grok Bot)

Copy the skill in [AGENTS.md](AGENTS.md) into the Bot description. Chat in plain language (`star the repo`, `open the repo`, `dummy files`). Known demos `start` directly. Anything else: `private-desk decide --utterance "…"`. The Bot runs the CLI on the **local computer**. If `doctor` is missing the CLI, keep the clone `.venv/bin` path in the skill.

Optional config: `~/.config/private-desk/config.toml` (never commit this). `setup` writes the same file.

```toml
inference = "local"
holo_bin = "holo"
holo_base_url = "http://127.0.0.1:8080/v1"
holo_model = "holo3-1-35b"
artifact_root = "~/Finance/inbox"   # optional; default is ~/.local/share/private-desk/inbox
repo_url = "https://github.com/jachian22/private-desk"
browser = "Google Chrome"           # menu-bar app name; Holo prompts interpolate {browser}
browser_profile = "private-desk"
allow_mutating = false
# typesafe_api_key = ""          # optional; or export TYPESAFE_API_KEY. doctor never prints it
```

## Local llama.cpp (a pet — you start it)

Bank and session-canary kinds need an OpenAI-compatible server on **loopback**. `private-desk` never forks `llama-server`. `doctor` and `start` of a local Holo kind tell you to boot it.

Known-good path: [H Company Mac recipe](https://hub.hcompany.ai/holo-desktop-cli/how-to/run-a-local-model-server) (Metal, Q4_K_M, ~21 GB weights). Bind `127.0.0.1` only — never `0.0.0.0`.

```bash
brew install llama.cpp
llama-server -hf Hcompany/Holo-3.1-35B-A3B-GGUF --host 127.0.0.1 \
  --n-gpu-layers 999 --ctx-size 65536 --batch-size 16384 --ubatch-size 2048 \
  --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 \
  --image-min-tokens 1024 --ctx-checkpoints 8 --cache-ram 32768 \
  --kv-unified --threads 16
```

Smoke: `curl -sS http://127.0.0.1:8080/v1/models`. `private-desk doctor` shows `local_model: reachable` when that answers. Hosted demos (`demo_open_repo`, `demo_star_repo`, `demo_post_x`) do not need the pet.

LM Studio (or any other OpenAI-compatible server) is optional: point `holo_base_url` at the same loopback URL. llama.cpp is the documented default.

Private kinds go in `~/.config/private-desk/kinds/` (not this repo). Copy `kinds/_session_canary.template.yaml`. The first canary we recommend is **GitHub**, `inference: local` only — hosted Holo is a spec violation for account kinds. Use `{browser}` and `{browser_profile}` from `private-desk setup`. Log in on the laptop if asked; Holo never types passwords.

Add a private bank kind the same way: YAML only under `~/.config/private-desk/kinds/`, never commit it, **local inference only**. Hosted Holo would send bank screens to H Company. Set `may_need_you: true`, `risk: read_only`, a tight `url_allowlist`, and `denied_actions` that include transfer, pay, send_money, wire, zelle, and submit_payment. `private-desk kinds` lists the schema, not the prompt. Do not put live bank YAML, statements, or screenshots in this repo. Do not hit a real bank in CI.

## Onboarding ladder

1. `private-desk setup --browser "…"` — once; kinds interpolate that app name
2. `private-desk start demo_dummy_files` — no Holo
3. `private-desk start demo_open_repo` — hosted Holo, public GitHub page (screens go to H Company)
4. `private-desk start demo_star_repo` — optional; needs `allow_mutating = true` and a GitHub login
5. `private-desk start demo_post_x --param message="testing.. this tweet was brought to you by Jev on a private desktop"` — optional; daily browser; ask first; `allow_mutating`; do not invent a different tweet
6. Private session canary — copy the template to config kinds (GitHub first); local llama.cpp; you log in on the laptop
7. Private bank kind — local Holo only

Grok Bot cron must **ask** before starting any `may_need_you` job. It must not run Holo on the cloud computer.

```bash
private-desk setup --browser "Google Chrome"
private-desk kinds
private-desk start demo_dummy_files --idempotency-key dummy-2026-08-27-a
private-desk get <job_id>
private-desk status
private-desk cancel <job_id>
private-desk resume <job_id>
private-desk decide --utterance "open the repo" --policy scripted
private-desk doctor              # missing Holo is a warning
private-desk doctor --strict
```
