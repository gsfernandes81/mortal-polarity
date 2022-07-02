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

"""Added lost sector settings table

Revision ID: 73bca89f337b
Revises: 93c9b7e168c5
Create Date: 2022-07-02 13:43:03.097809

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "73bca89f337b"
down_revision = "93c9b7e168c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lostsectorpostsettings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "autoannounce_enabled", sa.Boolean(), server_default="t", nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("lostsectorpostsettings")
