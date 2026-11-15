"""add pending status and request fingerprint

Revision ID: 7b1e4c2d9f30
Revises: 4cd9a890a352
Create Date: 2026-11-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b1e4c2d9f30'
down_revision: Union[str, Sequence[str], None] = '4cd9a890a352'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_CODE_CHECK = "ck_payments_authorization_code_matches_status"
AUTH_CODE_CHECK_SQL = "(status = 'Authorized') = (authorization_code IS NOT NULL)"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'Pending' BEFORE 'Authorized'")

    # server_default only to backfill existing rows, then dropped.
    op.add_column(
        'payments',
        sa.Column('request_fingerprint', sa.String(length=64), nullable=False, server_default=''),
    )
    op.alter_column('payments', 'request_fingerprint', server_default=None)


def downgrade() -> None:
    """Downgrade schema.

    Postgres can't drop an enum value, so the type is recreated. Pending rows
    can't be represented in the old schema and are deleted.
    """
    op.drop_column('payments', 'request_fingerprint')

    op.execute("DELETE FROM payments WHERE status = 'Pending'")
    # The check constraint references the enum type, so drop it while swapping types.
    op.drop_constraint(op.f(AUTH_CODE_CHECK), 'payments', type_='check')
    op.execute("ALTER TYPE payment_status RENAME TO payment_status_old")
    op.execute("CREATE TYPE payment_status AS ENUM ('Authorized', 'Declined')")
    op.execute(
        "ALTER TABLE payments ALTER COLUMN status TYPE payment_status "
        "USING status::text::payment_status"
    )
    op.execute("DROP TYPE payment_status_old")
    op.create_check_constraint(op.f(AUTH_CODE_CHECK), 'payments', AUTH_CODE_CHECK_SQL)
