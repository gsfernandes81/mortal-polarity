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

"""Updated XurPostSettings col names and added post_url

Revision ID: cea90a867173
Revises: 3236fcd1ba98
Create Date: 2022-07-17 13:01:57.012893

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "cea90a867173"
down_revision = "3236fcd1ba98"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "xurautopostchannel",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("server_id", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("xurpostsettings", sa.Column("post_url", sa.String(), nullable=True))
    op.alter_column(
        "xurpostsettings", "redirect_target", new_column_name="url_redirect_target"
    )

    op.alter_column(
        "xurpostsettings", "last_modified", new_column_name="url_last_modified"
    )
    op.alter_column(
        "xurpostsettings", "last_checked", new_column_name="url_last_checked"
    )
    op.alter_column(
        "xurpostsettings",
        "watcher_armed",
        new_column_name="url_watcher_armed",
    )


def downgrade() -> None:
    op.drop_table("xurautopostchannel")
    op.drop_column("xurpostsettings", "post_url")
    op.alter_column(
        "xurpostsettings", "url_redirect_target", new_column_name="redirect_target"
    )

    op.alter_column(
        "xurpostsettings", "url_last_modified", new_column_name="last_modified"
    )
    op.alter_column(
        "xurpostsettings", "url_last_checked", new_column_name="last_checked"
    )
    op.alter_column(
        "xurpostsettings",
        "url_watcher_armed",
        new_column_name="watcher_armed",
    )
