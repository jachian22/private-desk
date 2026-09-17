from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from private_desk import api
from private_desk.doctor import run_doctor
from private_desk.paths import job_dir
from private_desk.pythonpath import persist_src_pth


def _print_json(payload: dict[str, Any], *, force_json: bool) -> None:
    indent = None
    if sys.stdout.isatty() and not force_json:
        indent = 2
    elif force_json and sys.stdout.isatty():
        indent = 2
    sys.stdout.write(json.dumps(payload, indent=indent) + "\n")


def _parse_params(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(_fail_param(item))
        key, value = item.split("=", 1)
        out[key] = value
    return out


def _setup_wizard() -> tuple[str | None, str | None, str | None]:
    """TTY only. Ask for the strings later kinds interpolate into Holo prompts."""
    sys.stdout.write("App name as it appears in the menu bar (e.g. Google Chrome, Safari, Firefox):\n")
    sys.stdout.flush()
    browser = sys.stdin.readline().strip()
    sys.stdout.write("Profile name for account jobs (Enter keeps private-desk):\n")
    sys.stdout.flush()
    profile = sys.stdin.readline().strip()
    sys.stdout.write("Public repo URL for open/star demos (Enter keeps the default):\n")
    sys.stdout.flush()
    repo_url = sys.stdin.readline().strip()
    return browser or None, profile or None, repo_url or None


def _fail_param(item: str) -> int:
    payload = {
        "protocol": "private-desk/v0",
        "ok": False,
        "error": {"code": "kind_denied", "message": f"Expected key=value, got '{item}'."},
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    return 2


def _expand_job_id_argv(argv: list[str]) -> list[str]:
    """`private-desk job_…` is get. The first token is a subcommand, not the id."""
    for i, token in enumerate(argv):
        if token.startswith("-"):
            continue
        if token.startswith("job_"):
            return [*argv[:i], "get", token, *argv[i + 1 :]]
        break
    return argv


def main(argv: list[str] | None = None) -> int:
    persist_src_pth()
    argv = _expand_job_id_argv(list(sys.argv[1:] if argv is None else argv))
    parser = argparse.ArgumentParser(prog="private-desk", description="Private desktop jobs control plane.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON on stdout (already the default when stdout is not a TTY).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("kinds", help="List public kind metadata (never prompts).")

    p_start = sub.add_parser("start", help="Kick a job worker and return immediately.")
    p_start.add_argument("kind")
    p_start.add_argument("--param", action="append", default=[], metavar="key=value")
    p_start.add_argument("--idempotency-key", dest="idempotency_key")
    p_start.add_argument(
        "--wait",
        action="store_true",
        help="Stay in this terminal until the job leaves running, then print get.",
    )

    p_get = sub.add_parser("get", help="Get a job by id.")
    p_get.add_argument("job_id")

    p_wait = sub.add_parser("wait", help="Block until a job leaves running, then print get.")
    p_wait.add_argument("job_id")

    sub.add_parser("status", help="List running and needs_you jobs.")

    p_cancel = sub.add_parser("cancel", help="SIGTERM then SIGKILL the worker process group.")
    p_cancel.add_argument("job_id")

    p_resume = sub.add_parser("resume", help="Human finished the laptop action.")
    p_resume.add_argument("job_id")

    p_logs = sub.add_parser("logs", help="Print local worker log to this tty. Not for remote assistants.")
    p_logs.add_argument("job_id")

    p_doctor = sub.add_parser("doctor", help="Runtime checks. Missing Holo is a warning, not a failure.")
    p_doctor.add_argument(
        "--strict",
        action="store_true",
        help="Exit 5 if Holo or OS permissions are not ready.",
    )

    p_setup = sub.add_parser(
        "setup",
        help="Write local config: browser app name, profile, repo URL.",
    )
    p_setup.add_argument(
        "--browser",
        help='Menu-bar app name Holo should use, e.g. "Google Chrome", Safari, Firefox.',
    )
    p_setup.add_argument("--browser-profile", dest="browser_profile")
    p_setup.add_argument("--repo-url", dest="repo_url")

    args = parser.parse_args(argv)
    force_json = bool(args.json) or not sys.stdout.isatty()

    if args.cmd == "kinds":
        result = api.list_kinds()
    elif args.cmd == "start":
        try:
            params = _parse_params(args.param)
        except SystemExit as exc:
            return int(exc.code)
        result = api.start_job(args.kind, params, args.idempotency_key)
        if args.wait and result.ok:
            _print_json(result.payload, force_json=force_json)
            sys.stdout.flush()
            result = api.wait_job(result.payload["job"]["job_id"])
    elif args.cmd == "get":
        result = api.get_job(args.job_id)
    elif args.cmd == "wait":
        result = api.wait_job(args.job_id)
    elif args.cmd == "status":
        result = api.status_jobs()
    elif args.cmd == "cancel":
        result = api.cancel_job(args.job_id)
    elif args.cmd == "resume":
        result = api.resume_job(args.job_id)
    elif args.cmd == "logs":
        result = api.job_logs(args.job_id)
        _print_json(result.payload, force_json=True)
        log_file = job_dir(args.job_id) / "worker.log"
        if result.ok and sys.stdout.isatty() and log_file.is_file():
            sys.stdout.write("\n--- worker.log (laptop tty only) ---\n")
            sys.stdout.write(log_file.read_text())
        return result.exit_code
    elif args.cmd == "doctor":
        payload = run_doctor(strict=args.strict)
        exit_code = int(payload.pop("exit_code", 0))
        _print_json(payload, force_json=force_json)
        return exit_code
    elif args.cmd == "setup":
        browser = args.browser
        profile = args.browser_profile
        repo_url = args.repo_url
        if (
            browser is None
            and profile is None
            and repo_url is None
            and sys.stdin.isatty()
            and sys.stdout.isatty()
        ):
            browser, profile, repo_url = _setup_wizard()
        result = api.setup_config(
            browser=browser,
            browser_profile=profile,
            repo_url=repo_url,
        )
    else:
        parser.error("unknown command")
        return 1

    _print_json(result.payload, force_json=force_json)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
