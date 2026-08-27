from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from private_desk import api
from private_desk.doctor import run_doctor
from private_desk.paths import job_dir


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


def _fail_param(item: str) -> int:
    payload = {
        "protocol": "private-desk/v0",
        "ok": False,
        "error": {"code": "kind_denied", "message": f"Expected key=value, got '{item}'."},
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
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

    p_get = sub.add_parser("get", help="Get a job by id.")
    p_get.add_argument("job_id")

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
    elif args.cmd == "get":
        result = api.get_job(args.job_id)
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
    else:
        parser.error("unknown command")
        return 1

    _print_json(result.payload, force_json=force_json)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
