"""Interest profiles: profile / screening_model / rubric_answers; archive the PV queue

Revision ID: 006
Revises: 005
Create Date: 2026-11-15

Literature monitoring moves from pharmacovigilance to a new field, with the
active field chosen by an interest profile (content_screening/profiles/). Every
article now records which profile and which model screened it, so training data
from the two fields is never mixed by accident and models can be compared.

- `profile`: backfilled to 'pv' on every existing row.
- `screening_model`: backfilled from the code history. The default flash model
  was deepseek/deepseek-v4-flash until PR #187 (deepseek/deepseek-v4.1-flash)
  merged at 2026-09-20 09:43 +02:00. The split is by `discovered_at`, so a row
  screened between that merge and the server picking it up is mislabelled
  v4.1; at most a day or so of scans.
- `rubric_answers`: raw per-statement rubric answers (JSON). NULL for PV rows,
  which were scored by the old relevance/confidence prompt.
- The never-triaged PV `pending` queue (2,348 rows on 2026-11-14) moves to the
  new `archived` status. Kept/dismissed decisions, auto_rejected rows and all
  embeddings are untouched.

Revises 005 (reMarkable/Drive columns, on the drive-outbound branch), which
must land first.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 2026-09-20T09:43:16+02:00, when PR #187 merged to main.
V41_FLASH_FROM_EPOCH = 1789890196


def upgrade() -> None:
    op.add_column("articles", sa.Column("profile", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("screening_model", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("rubric_answers", sa.Text(), nullable=True))
    op.create_index("idx_articles_profile", "articles", ["profile", "status"])

    op.execute("UPDATE articles SET profile = 'pv'")
    op.execute(
        "UPDATE articles SET screening_model = CASE"
        f" WHEN discovered_at < {V41_FLASH_FROM_EPOCH}"
        " THEN 'deepseek/deepseek-v4-flash'"
        " ELSE 'deepseek/deepseek-v4.1-flash' END"
    )
    op.execute("UPDATE articles SET status = 'archived' WHERE status = 'pending'")


def downgrade() -> None:
    # Lossless while no new-profile rows exist: every archived row was pending.
    op.execute("UPDATE articles SET status = 'pending' WHERE status = 'archived'")
    op.drop_index("idx_articles_profile", table_name="articles")
    op.drop_column("articles", "rubric_answers")
    op.drop_column("articles", "screening_model")
    op.drop_column("articles", "profile")
