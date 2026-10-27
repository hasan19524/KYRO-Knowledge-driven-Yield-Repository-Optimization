"""github oauth identity columns on users

Additive only: two nullable columns (github_id, github_login) recording
which GitHub account created/linked a user via "Sign in with GitHub".
Existing rows are untouched; email/password and API-key authentication
are unchanged. The OAuth access token is never persisted.

Revision ID: d4e5f6a7b8c9
Revises: b8e4c1f07a23
Create Date: 2026-10-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "b8e4c1f07a23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("github_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("github_login", sa.Text(), nullable=True))
    # Unnamed => PostgreSQL default name (users_github_id_key), matching
    # the model's unique=True so metadata and schema stay aligned.
    op.create_unique_constraint(None, "users", ["github_id"])


def downgrade() -> None:
    op.drop_constraint("users_github_id_key", "users", type_="unique")
    op.drop_column("users", "github_login")
    op.drop_column("users", "github_id")
