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

"""Added url update code for XurPostSettings

Revision ID: 3236fcd1ba98
Revises: e9b61bf2db56
Create Date: 2022-07-16 16:31:36.561413

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3236fcd1ba98"
down_revision = "e9b61bf2db56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("xurpostsettings", sa.Column("url", sa.String(), nullable=True))
    op.add_column(
        "xurpostsettings", sa.Column("redirect_target", sa.String(), nullable=True)
    )
    op.add_column(
        "xurpostsettings", sa.Column("last_modified", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "xurpostsettings", sa.Column("last_checked", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "xurpostsettings",
        sa.Column("watcher_armed", sa.Boolean(), server_default="f", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("xurpostsettings", "watcher_armed")
    op.drop_column("xurpostsettings", "last_checked")
    op.drop_column("xurpostsettings", "last_modified")
    op.drop_column("xurpostsettings", "redirect_target")
    op.drop_column("xurpostsettings", "url")
