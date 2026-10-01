"""Daily words shown on the TRMNL panel

Revision ID: 002
Revises: 001
Create Date: 2026-10-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_words",
        sa.Column("date", sa.String(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("word_to_learn", sa.Text(), nullable=False),
        sa.Column("word_class", sa.Text(), nullable=False),
        sa.Column("translation", sa.Text(), nullable=False),
        sa.Column("example_sv", sa.Text(), nullable=False),
        sa.Column("example_en", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("date", "slot"),
    )


def downgrade() -> None:
    op.drop_table("daily_words")
