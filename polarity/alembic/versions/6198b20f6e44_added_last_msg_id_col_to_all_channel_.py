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

"""Added last_msg_id col to all channel tables

Revision ID: 6198b20f6e44
Revises: cea90a867173
Create Date: 2022-07-17 17:14:48.999377

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "6198b20f6e44"
down_revision = "cea90a867173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lostsectorautopostchannel",
        sa.Column("last_msg_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "xurautopostchannel", sa.Column("last_msg_id", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("xurautopostchannel", "last_msg_id")
    op.drop_column("lostsectorautopostchannel", "last_msg_id")
