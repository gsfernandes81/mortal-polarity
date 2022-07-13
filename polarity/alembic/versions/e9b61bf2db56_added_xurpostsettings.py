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

"""Added XurPostSettings

Revision ID: e9b61bf2db56
Revises: 994928bdc1a8
Create Date: 2022-07-10 17:34:39.715914

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e9b61bf2db56"
down_revision = "994928bdc1a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "xurpostsettings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "autoannounce_enabled", sa.Boolean(), server_default="t", nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("xurpostsettings")
