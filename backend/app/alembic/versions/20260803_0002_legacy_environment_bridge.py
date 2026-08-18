"""Bridge a legacy deployed Alembic marker into the repository history.

Revision ID: 20260803_0002
Revises: c7a4e8d12f60
Create Date: 2026-08-03 00:02:00.000000

Some deployed databases were stamped with this revision after the IAM/RBAC
baseline, but the source file was not retained in the repository. The deployed
schema has been verified to contain the complete c7a4e8d12f60 structure. This
no-op bridge makes that historical marker explicit and keeps future upgrades
auditable without rewriting alembic_version manually.
"""

revision = "20260803_0002"
down_revision = "c7a4e8d12f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
