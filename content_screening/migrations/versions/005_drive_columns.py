"""Add reMarkable/Drive routing columns to articles

Revision ID: 005
Revises: 004
Create Date: 2026-11-15

Kept papers are also sent to the reMarkable, via the photos account's Drive
(`reMarkable/Papers/To read`), with a cover page summarising the screening:
- `drive_file_id`: the uploaded PDF's Drive file ID once sent.
- `drive_error`: the last failure, for the triage card and the retry loop.
- `pdf_unavailable`: no open-access PDF could be found (paywalled). Routing to
  Drive is then complete without an upload, and the stub goes to `paywalled/`.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("drive_file_id", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("drive_error", sa.Text(), nullable=True))
    op.add_column(
        "articles",
        sa.Column("pdf_unavailable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("articles", "pdf_unavailable")
    op.drop_column("articles", "drive_error")
    op.drop_column("articles", "drive_file_id")
