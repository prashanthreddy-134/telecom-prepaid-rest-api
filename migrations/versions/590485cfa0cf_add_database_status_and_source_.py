
"""add database status and source constraints

Revision ID: 590485cfa0cf
Revises: 895094a11573
"""

from typing import Sequence, Union

from alembic import op


revision: str = "590485cfa0cf"
down_revision: Union[str, Sequence[str], None] = "895094a11573"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch table recreation to add CHECK constraints.
    with op.batch_alter_table(
        "recharges",
        recreate="always",
    ) as batch_op:
        batch_op.create_check_constraint(
            "ck_recharge_status",
            "status IN ('success')",
        )

    with op.batch_alter_table(
        "complaints",
        recreate="always",
    ) as batch_op:
        batch_op.create_check_constraint(
            "ck_complaint_source",
            "source IN ('app', 'call_centre', 'web')",
        )
        batch_op.create_check_constraint(
            "ck_complaint_status",
            "status IN ('open', 'in_progress', 'resolved', 'rejected')",
        )

    with op.batch_alter_table(
        "usage_records",
        recreate="always",
    ) as batch_op:
        batch_op.create_check_constraint(
            "ck_usage_source_unit",
            "source_unit IN ('MB', 'GB')",
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "usage_records",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_usage_source_unit",
            type_="check",
        )

    with op.batch_alter_table(
        "complaints",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_complaint_status",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_complaint_source",
            type_="check",
        )

    with op.batch_alter_table(
        "recharges",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_recharge_status",
            type_="check",
        )
