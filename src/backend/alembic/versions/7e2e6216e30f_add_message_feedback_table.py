"""add message_feedback table

Revision ID: 7e2e6216e30f
Revises: 683a0e0798a4
Create Date: 2026-05-18 20:40:34.979100

"""

from typing import Sequence, Union

import sqlmodel
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7e2e6216e30f"
down_revision: Union[str, Sequence[str], None] = "683a0e0798a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "message_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column(
            "message_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False
        ),
        sa.Column(
            "user_id", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column("rating", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column(
            "comment", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        # The unique composite index on (message_id, user_id) is the only
        # lookup path used today (single-row in the router, IN-list in
        # sessions.py), so no separate per-column indexes are needed.
        sa.UniqueConstraint(
            "message_id", "user_id", name="uq_message_feedback_msg_user"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("message_feedback")
