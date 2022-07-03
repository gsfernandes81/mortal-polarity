# Copyright © 2019-present gsfernandes81

# This file is part of "mortal-polarity".

# mortal-polarity is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later version.

# "mortal-polarity" is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License along with
# mortal-polarity. If not, see <https://www.gnu.org/licenses/>.

"""Removed the AutopostServers table

Revision ID: 994928bdc1a8
Revises: 17b9c71c9e71
Create Date: 2022-07-03 13:19:49.844337

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "994928bdc1a8"
down_revision = "17b9c71c9e71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("autopostservers")
    op.rename_table("lostsectorautopostchannels", "lostsectorautopostchannel")
    op.add_column(
        "lostsectorautopostchannel", sa.Column("server_id", sa.BIGINT(), nullable=True)
    )
    op.add_column(
        "lostsectorautopostchannel", sa.Column("enabled", sa.BOOLEAN(), nullable=True)
    )


def downgrade() -> None:
    op.create_table(
        "autopostservers",
        sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "enabled",
            sa.BOOLEAN(),
            server_default=sa.text("true"),
            autoincrement=False,
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="autopostservers_pkey"),
    )
    op.drop_column("lostsectorautopostchannel", "server_id")
    op.drop_column("lostsectorautopostchannel", "enabled")
    op.rename_table("lostsectorautopostchannel", "lostsectorautopostchannels")
