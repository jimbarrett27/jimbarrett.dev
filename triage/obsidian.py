"""Writes Obsidian stub notes for triaged papers.

A ``kept`` (or legacy ``deep``/``filed``) decision produces a markdown stub in
``<vault>/literature/inbox/unread/<YYYY-MM-DD>-<slug>.md`` with frontmatter the
rest of the vault can query, and the relevance reason as the body. Obsidian
remains the editor — these are just filed stubs. The sibling ``read/`` subfolder
is populated manually by the user; the app never writes or reads it.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from content_screening.orm_models import ArticleORM

DEFAULT_INBOX_SUBDIR = "literature/inbox"
UNREAD_SUBDIR = "unread"
# Kept papers with no open-access PDF, which therefore didn't go to the reMarkable.
PAYWALLED_SUBDIR = "paywalled"
SLUG_MAX_LEN = 60

# Obsidian frontmatter `status` per decision.
# Legacy entries (`deep`, `filed`) remain so half-routed old rows still render
# correctly; new decisions use `kept` → `unread`.
_STATUS_BY_DECISION = {"kept": "unread", "deep": "to-read", "filed": "filed"}


def slugify(title: str) -> str:
    """Lowercase, non-alphanumerics → hyphens, truncated to 60 chars."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:SLUG_MAX_LEN].rstrip("-") or "untitled"


def _epoch_to_date(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()


def _iso_to_date(iso: str) -> str:
    return datetime.fromisoformat(iso).date().isoformat()


def build_stub_markdown(paper: ArticleORM) -> str:
    """Render the full markdown (frontmatter + body) for a paper's stub."""
    frontmatter = {
        "title": paper.title,
        # How the reMarkable pipeline finds the stub after you've moved it.
        "triage_id": paper.id,
        "authors": list(paper.authors or []),
        "source": paper.source_type,
        "url": paper.url,
        "discovered": _epoch_to_date(paper.discovered_at),
        "triaged": _iso_to_date(paper.decided_at) if paper.decided_at else None,
        "status": _STATUS_BY_DECISION.get(paper.status, paper.status),
        "zotero": paper.zotero_key or "",
        "tags": ["paper", f"triage/{paper.status}"],
    }
    fm = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    reason = paper.llm_reasoning or "(no reason recorded)"
    paywalled = ""
    if paper.pdf_unavailable:
        paywalled = (
            "> [!note] No open-access PDF\n"
            "> To read it on the reMarkable, upload the PDF to `reMarkable/Papers/To read` "
            f"named `{paper.id} - <title>.pdf`.\n\n"
        )
    return (
        f"---\n{fm}\n---\n\n"
        f"# {paper.title}\n\n"
        f"> **Why this surfaced:** {reason}\n\n"
        f"{paywalled}"
        f"## Notes\n\n"
        f"<!-- (empty — to be filled when read) -->\n"
    )


def write_stub(
    vault_root: Path, paper: ArticleORM, inbox_subdir: str = DEFAULT_INBOX_SUBDIR
) -> str:
    """Write a new stub file and return its path relative to the vault root.

    Collisions (same date + slug) get a ``-2``, ``-3`` … suffix. This always
    creates a fresh file; idempotency (skip if already written) is the caller's
    responsibility via ``ArticleORM.obsidian_path``.
    """
    inbox = vault_root / inbox_subdir / (PAYWALLED_SUBDIR if paper.pdf_unavailable else UNREAD_SUBDIR)
    inbox.mkdir(parents=True, exist_ok=True)

    date = _iso_to_date(paper.decided_at) if paper.decided_at else (
        datetime.now(timezone.utc).date().isoformat()
    )
    base = f"{date}-{slugify(paper.title)}"

    filename = f"{base}.md"
    counter = 2
    while (inbox / filename).exists():
        filename = f"{base}-{counter}.md"
        counter += 1

    path = inbox / filename
    path.write_text(build_stub_markdown(paper), encoding="utf-8")
    return str(path.relative_to(vault_root))


def move_to_paywalled(
    vault_root: Path, rel_path: str, inbox_subdir: str = DEFAULT_INBOX_SUBDIR
) -> str:
    """Move a stub we wrote into ``paywalled/``; its new vault-relative path.

    Only a stub still where we put it is moved: if it's gone (you've already moved
    it yourself), it's left alone and the old path is returned.
    """
    src = vault_root / rel_path
    if not src.exists():
        return rel_path
    dest_dir = vault_root / inbox_subdir / PAYWALLED_SUBDIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        return rel_path
    src.rename(dest)
    return str(dest.relative_to(vault_root))
