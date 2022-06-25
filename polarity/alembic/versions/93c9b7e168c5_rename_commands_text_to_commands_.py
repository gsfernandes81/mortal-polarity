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

"""Rename commands.text to commands.response

Revision ID: 93c9b7e168c5
Revises: 5314339d0745
Create Date: 2022-06-25 13:42:11.034486

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "93c9b7e168c5"
down_revision = "5314339d0745"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("commands", "text", nullable=False, new_column_name="response")


def downgrade() -> None:
    op.alter_column("commands", "response", nullable=False, new_column_name="text")
