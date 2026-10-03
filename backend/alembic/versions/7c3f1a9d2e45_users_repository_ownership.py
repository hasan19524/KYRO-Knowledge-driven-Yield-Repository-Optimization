"""users table + repository ownership

Adds KYRO user accounts and links every repository to its owning user.

  * `users` is created and seeded with the legacy `default` user that the
    shared service key (KYRO_API_KEY) maps to.
  * `repositories.owner_user_id` is added as a nullable FK so no existing
    row is touched destructively; pre-existing repositories are backfilled
    to `default` (single-tenant history -> only possible owner).
  * Rows the ingestion worker creates without onboarding stay unowned
    (owner_user_id IS NULL) and are invisible to per-user identities.

Revision ID: 7c3f1a9d2e45
Revises: 0f9d27246cef
Create Date: 2026-10-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "7c3f1a9d2e45"
down_revision: Union[str, None] = "0f9d27246cef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("handle", sa.Text(), nullable=False),
        sa.Column("api_key_hash", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handle"),
        sa.UniqueConstraint("api_key_hash"),
    )
    # Legacy identity: shared KYRO_API_KEY / development mode resolves here.
    op.execute(
        "INSERT INTO users (handle, api_key_hash, is_active, created_at, "
        "updated_at) VALUES ('default', NULL, TRUE, now(), now())"
    )
    op.add_column(
        "repositories", sa.Column("owner_user_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_repositories_owner_user_id",
        "repositories",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_repositories_owner_user_id", "repositories", ["owner_user_id"])
    # Non-destructive backfill: every repository that already exists predates
    # per-user ownership, so the legacy identity is its unambiguous owner.
    op.execute(
        "UPDATE repositories SET owner_user_id = "
        "(SELECT id FROM users WHERE handle = 'default')"
    )


def downgrade() -> None:
    op.drop_index("ix_repositories_owner_user_id", table_name="repositories")
    op.drop_constraint(
        "fk_repositories_owner_user_id", "repositories", type_="foreignkey"
    )
    op.drop_column("repositories", "owner_user_id")
    op.drop_table("users")
