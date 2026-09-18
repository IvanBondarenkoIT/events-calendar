from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from dec_calendar.config import REPO_ROOT, load_settings
from dec_calendar.import_service import build_import_drafts, run_import, run_import_extra
from dec_calendar.jira_client import JiraClient
from dec_calendar.job import run_reminder_job
from dec_calendar.models import AlertSlot


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def cmd_check_config(_: argparse.Namespace) -> int:
    settings = load_settings()
    print(f"timezone={settings.timezone}")
    print(f"jira_url={settings.jira_url or '(empty)'}")
    print(f"jira_project={settings.jira_project_key}")
    print(f"jira_email_set={bool(settings.jira_email)}")
    print(f"jira_token_set={bool(settings.jira_api_token)}")
    print(f"telegram_token_set={bool(settings.telegram_bot_token)}")
    print(f"telegram_chat_set={bool(settings.telegram_chat_id)}")
    print(f"notify_via_hub={settings.notify_via_hub}")
    print(f"notify_hub_url={settings.notify_hub_url or '(empty)'}")
    print(f"notify_hub_key_set={bool(settings.notify_hub_api_key)}")
    print(f"dry_run={settings.dry_run}")
    print(f"idempotency_path={settings.idempotency_path}")
    return 0


def cmd_check_jira(_: argparse.Namespace) -> int:
    settings = load_settings()
    client = JiraClient(settings)
    me = client.get_myself()
    print(f"authenticated_as={me.get('displayName')} <{me.get('emailAddress')}>")
    project = client.get_project()
    print(f"project={project.get('key')} — {project.get('name')}")
    return 0


def cmd_preview_import(args: argparse.Namespace) -> int:
    today = _parse_date(args.today)
    drafts = build_import_drafts(today=today)
    dated = [d for d in drafts if d.due_date and not d.needs_date]
    needs = [d for d in drafts if d.needs_date]
    print(f"total={len(drafts)} dated={len(dated)} needs_date={len(needs)}")
    for d in drafts:
        due = d.due_date.isoformat() if d.due_date else "NO_DATE"
        flags = ",".join(d.labels)
        print(f"- {due} | {d.kind.value:8} | {d.summary} | {flags}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    settings = load_settings()
    dry = bool(args.dry_run) or settings.dry_run
    result = run_import(
        settings,
        dry_run=dry,
        today=_parse_date(args.today),
        replace=bool(args.replace),
    )
    print(f"created={len(result.created)} skipped={len(result.skipped_existing)} failed={len(result.failed)}")
    for key in result.created:
        print(f"  + {key}")
    for key in result.skipped_existing:
        print(f"  = {key}")
    for summary, err in result.failed:
        print(f"  ! {summary}: {err}")
    return 1 if result.failed else 0


def cmd_import_extra(args: argparse.Namespace) -> int:
    settings = load_settings()
    dry = bool(args.dry_run) or settings.dry_run
    result = run_import_extra(settings, dry_run=dry)
    print(
        f"created={len(result.created)} updated={len(result.updated)} "
        f"skipped={len(result.skipped_existing)} failed={len(result.failed)}"
    )
    for key in result.created:
        print(f"  + {key}")
    for key in result.updated:
        print(f"  ~ {key}")
    for key in result.skipped_existing:
        print(f"  = {key}")
    for summary, err in result.failed:
        print(f"  ! {summary}: {err}")
    return 1 if result.failed else 0


def cmd_run_once(args: argparse.Namespace) -> int:
    settings = load_settings()
    dry = bool(args.dry_run) or settings.dry_run
    slot = AlertSlot(args.slot)
    report = run_reminder_job(
        settings,
        dry_run=dry,
        today=_parse_date(args.today),
        slot=slot,
        comment_on_jira=not args.no_jira_comment,
    )
    print(f"today={report.today.isoformat()} slot={report.slot} considered={report.considered}")
    print(
        f"sent={len(report.sent)} dry_planned={len(report.dry_run_planned)} "
        f"skipped={len(report.skipped_already_sent)} errors={len(report.errors)}"
    )
    for action in report.sent + report.dry_run_planned:
        prefix = "DRY" if action in report.dry_run_planned else "SENT"
        print(f"  [{prefix}] {action.issue_key} {action.window}: {action.summary}")
    for err in report.errors:
        print(f"  ERROR {err}")
    return 1 if report.errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dec-calendar",
        description="DimKava Event Calendar (DEC): Jira SSOT + Telegram reminders",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check-config", help="Show whether required env vars are set")
    p.set_defaults(func=cmd_check_config)

    p = sub.add_parser("check-jira", help="Authenticate and verify project DEC exists")
    p.set_defaults(func=cmd_check_jira)

    p = sub.add_parser("preview-import", help="Parse Excel + birthdays without calling Jira")
    p.add_argument("--today", help="Override today YYYY-MM-DD (for birthday year)")
    p.set_defaults(func=cmd_preview_import)

    p = sub.add_parser("import-events", help="Import drafts into Jira DEC (idempotent by summary)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--today", help="Override today YYYY-MM-DD")
    p.add_argument(
        "--replace",
        action="store_true",
        help="Delete all existing DEC calendar issues, then import chronologically",
    )
    p.set_defaults(func=cmd_import)

    p = sub.add_parser(
        "import-extra",
        help="Create/update manual DK extras in listed order (no chronological sort)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_import_extra)

    p = sub.add_parser("run-once", help="Evaluate reminder windows and send Telegram alerts")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--today", help="Override today YYYY-MM-DD (for tests)")
    p.add_argument(
        "--slot",
        choices=["morning", "evening", "auto"],
        default="auto",
        help="Alert slot: morning(10:00), evening(22:00), auto by local hour",
    )
    p.add_argument("--no-jira-comment", action="store_true")
    p.set_defaults(func=cmd_run_once)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Ensure src/ is importable when run as python -m from repo or via path
    src = REPO_ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()
    _setup_logging(settings.log_level)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
