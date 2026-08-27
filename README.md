# private-desk

Privacy-preserving desktop jobs for a consumer assistant (Grok Bot first), powered by [HoloDesktop](https://github.com/hcompai/holo-desktop-cli). The assistant **kicks** a job on your laptop and never sees the screen.

Law: [SPEC.md](SPEC.md). Agents: [AGENTS.md](AGENTS.md). License: [Apache-2.0](LICENSE).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
private-desk doctor
```

Optional config: `~/.config/private-desk/config.toml` (never commit this).

```toml
inference = "local"
holo_bin = "holo"
holo_base_url = "http://127.0.0.1:8080/v1"
holo_model = "holo3-1-35b"
artifact_root = "~/Finance/inbox"   # optional; default is ~/.local/share/private-desk/inbox
repo_url = "https://github.com/YOUR_USER/private-desk"
browser_profile = "private-desk"
allow_mutating = false
```

Private bank kinds go in `~/.config/private-desk/kinds/`. Do not add them to this repo. Copy `kinds/_session_canary.template.yaml`.

## Onboarding ladder

1. `private-desk start demo_dummy_files` — no Holo
2. `private-desk start demo_open_repo` — hosted Holo, public GitHub page (screens go to H Company)
3. `private-desk start demo_star_repo` — optional; needs `allow_mutating = true` and a GitHub login
4. Private session canary — local Holo; you log in on the laptop
5. Private bank kind — local Holo only

Grok Bot cron must **ask** before starting any `may_need_you` job. It must not run Holo on the cloud computer.

```bash
private-desk kinds
private-desk start demo_dummy_files --idempotency-key dummy-2026-08-27
private-desk get <job_id>
private-desk status
private-desk cancel <job_id>
private-desk resume <job_id>
private-desk doctor              # missing Holo is a warning
private-desk doctor --strict
```
