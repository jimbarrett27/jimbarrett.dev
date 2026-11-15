"""One-off: add ``triage_id`` to Obsidian stubs written before it existed.

Run with::

    uv run python -m triage.backfill_stub_ids            # report only
    uv run python -m triage.backfill_stub_ids --apply    # write

Stubs are moved by hand between ``unread/``, ``read/`` and ``paywalled/``, so
they are matched to their paper by content, not location: first the path
recorded on the paper (``obsidian_path``), then the URL, then the normalised
title. Only the ``triage_id:`` line is added, directly after the title, so the
rest of the frontmatter keeps its formatting. Stubs that already have one, or
that match no paper (or several), are left alone and listed. The database is
not written. Re-running is safe: a second pass finds nothing to do.
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select

from content_screening.db_engine import get_session
from content_screening.orm_models import ArticleORM
from triage.config import get_settings

_ROUTED_STATUSES = ("kept", "deep", "filed")
_TOP_LEVEL_KEY = re.compile(r"^[A-Za-z_][\w-]*:")


@dataclass
class Plan:
    path: Path
    paper_id: Optional[int]
    reason: str  # how it matched, or why it was skipped


def _normalise(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def split_frontmatter(text: str) -> Optional[tuple[list[str], str]]:
    """(frontmatter lines, rest of the file) or None if there is no frontmatter."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return text[4:end].split("\n"), text[end:]


def add_triage_id(text: str, paper_id: int) -> Optional[str]:
    """``text`` with ``triage_id: <paper_id>`` after the title (or first) key."""
    parts = split_frontmatter(text)
    if parts is None:
        return None
    lines, rest = parts
    keys = [i for i, line in enumerate(lines) if _TOP_LEVEL_KEY.match(line)]
    if not keys:
        return None
    # Insert before the key that follows `title` (titles can wrap over lines).
    title_at = next((i for i in keys if lines[i].startswith("title:")), None)
    following = [i for i in keys if title_at is not None and i > title_at]
    at = following[0] if following else (keys[0] if title_at is None else len(lines))
    lines = lines[:at] + [f"triage_id: {paper_id}"] + lines[at:]
    return "---\n" + "\n".join(lines) + rest


def plan_backfill(root: Path, vault: Path, papers: list[ArticleORM]) -> list[Plan]:
    """Decide, for every stub under ``root``, which paper it belongs to."""
    by_path = {p.obsidian_path: p.id for p in papers if p.obsidian_path}
    by_url: dict[str, set[int]] = {}
    by_title: dict[str, set[int]] = {}
    for p in papers:
        by_url.setdefault(p.url, set()).add(p.id)
        by_title.setdefault(_normalise(p.title), set()).add(p.id)

    plans = []
    for path in sorted(root.rglob("*.md")):
        parts = split_frontmatter(path.read_text(encoding="utf-8"))
        if parts is None:
            plans.append(Plan(path, None, "skipped: no frontmatter"))
            continue
        try:
            fm = yaml.safe_load("\n".join(parts[0])) or {}
        except yaml.YAMLError:
            plans.append(Plan(path, None, "skipped: unreadable frontmatter"))
            continue
        if not isinstance(fm, dict):
            plans.append(Plan(path, None, "skipped: unreadable frontmatter"))
            continue
        if fm.get("triage_id") is not None:
            plans.append(Plan(path, None, "skipped: already has triage_id"))
            continue

        rel = str(path.relative_to(vault))
        if rel in by_path:
            plans.append(Plan(path, by_path[rel], "matched by recorded path"))
            continue
        for label, index, key in (("URL", by_url, fm.get("url")),
                                  ("title", by_title, _normalise(str(fm.get("title") or "")))):
            ids = index.get(key) if key else None
            if ids and len(ids) == 1:
                plans.append(Plan(path, next(iter(ids)), f"matched by {label}"))
                break
            if ids:
                plans.append(Plan(path, None, f"skipped: {label} matches papers {sorted(ids)}"))
                break
        else:
            plans.append(Plan(path, None, "skipped: no matching paper"))
    return plans


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.obsidian_vault:
        raise SystemExit("TRIAGE_OBSIDIAN_VAULT is not set")
    vault = Path(settings.obsidian_vault)
    root = vault / settings.obsidian_inbox_subdir

    with get_session() as session:
        papers = list(session.scalars(
            select(ArticleORM).where(ArticleORM.status.in_(_ROUTED_STATUSES))
        ))
        session.expunge_all()

    plans = plan_backfill(root, vault, papers)
    todo = [p for p in plans if p.paper_id is not None]
    for plan in plans:
        target = f"-> {plan.paper_id}" if plan.paper_id is not None else ""
        print(f"{plan.path.relative_to(vault)}  {plan.reason} {target}".rstrip())

    if args.apply:
        for plan in todo:
            text = add_triage_id(plan.path.read_text(encoding="utf-8"), plan.paper_id)
            plan.path.write_text(text, encoding="utf-8")
    verb = "Added" if args.apply else "Would add"
    print(f"\n{verb} triage_id to {len(todo)} of {len(plans)} stubs."
          + ("" if args.apply else " Run with --apply to write."))


if __name__ == "__main__":
    main()
