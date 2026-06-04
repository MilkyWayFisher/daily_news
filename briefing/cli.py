from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from briefing.config import load_config
from briefing.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    _configure_pipe_encoding()
    parser = argparse.ArgumentParser(description="Generate the daily investment intelligence brief.")
    parser.add_argument("--config", default=None, help="Path to config.yaml, config.yml, or config.json")
    parser.add_argument("--date", default=None, help="Brief date, default: today")
    parser.add_argument("--demo", action="store_true", help="Use sample news when API data is unavailable")
    parser.add_argument("--dry-run", action="store_true", help="Do not send delivery messages")
    parser.add_argument("--no-save", action="store_true", help="Do not write output files")
    parser.add_argument("--env", default=".env", help="Optional .env file to load")
    parser.add_argument("--check-delivery", action="store_true", help="Check delivery settings without generating a brief")
    args = parser.parse_args(argv)

    _load_env_file(args.env)
    config = load_config(args.config)
    if args.check_delivery:
        return _check_delivery(config.delivery.channel)

    result = run_pipeline(
        config,
        run_date=args.date,
        demo=args.demo,
        dry_run=args.dry_run,
        save=not args.no_save,
    )
    print(result.markdown)
    if result.saved_dir:
        print(f"\nSaved to: {result.saved_dir}")
    if not args.dry_run:
        print(f"Delivered: {result.delivered}")
        if not result.delivered:
            _print_delivery_diagnostics(config.delivery.channel)
            return 1
    return 0


def _print_delivery_diagnostics(channel: str) -> None:
    if channel.lower() == "email":
        from briefing.delivery import EmailDelivery

        delivery = EmailDelivery()
        missing = delivery.missing_settings
        if missing:
            print("Email delivery is missing: " + ", ".join(missing))
        else:
            check = delivery.check_connection()
            print("Email delivery is configured, but SMTP send failed.")
            print("SMTP diagnostic: " + check.message)


def _check_delivery(channel: str) -> int:
    if channel.lower() == "email":
        from briefing.delivery import EmailDelivery

        check = EmailDelivery().check_connection()
        print(check.message)
        return 0 if check.ok else 1
    print(f"No delivery check implemented for channel: {channel}")
    return 1


def _load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _configure_pipe_encoding() -> None:
    if sys.stdout.isatty() or not hasattr(sys.stdout, "reconfigure"):
        return
    sys.stdout.reconfigure(encoding="utf-8")
