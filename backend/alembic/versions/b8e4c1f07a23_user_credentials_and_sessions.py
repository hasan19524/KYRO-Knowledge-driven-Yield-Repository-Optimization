"""user credentials (email/password) + login sessions

Additive only: two nullable columns on `users` (email, PBKDF2
password_hash) plus a new `user_sessions` table. Existing rows are never
touched; API-key authentication (users.api_key_hash) is unchanged. Only
SHA-256 hashes of session tokens are ever stored.

Revision ID: b8e4c1f07a23
Revises: 7c3f1a9d2e45
Create Date: 2026-10-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8e4c1f07a23"
down_revision: Union[str, None] = "7c3f1a9d2e45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    # Unnamed => PostgreSQL's default name (users_email_key), matching the
    # model's unique=True so metadata and schema stay aligned.
    op.create_unique_constraint(None, "users", ["email"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
