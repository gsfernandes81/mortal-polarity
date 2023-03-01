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

import hikari as h
import lightbulb as lb
import json
from json import encoder
from . import ls, weekly_reset, xur
from .utils import db_session
from sqlalchemy import select

from . import cfg, controller


@controller.kyber.child
@lb.command("export", "Export db channels", inherit_checks=True, auto_defer=True)
@lb.implements(lb.SlashSubCommand)
async def export(ctx: lb.Context):
    """Export the bot's data to a JSON file."""
    await ctx.respond("Exporting...")
    for channel_id, cls in [
        (cfg.ls_follow_channel_id, ls.LostSectorAutopostChannel),
        (cfg.reset_follow_channel_id, weekly_reset.WeeklyResetAutopostChannel),
        (cfg.xur_follow_channel_id, xur.XurAutopostChannel),
    ]:
        async with db_session() as session:
            async with session.begin():
                channel_id_list = (
                    await session.execute(select(cls).where(cls.enabled == True))
                ).fetchall()
                channel_id_list = [] if channel_id_list is None else channel_id_list
                channel_id_list = [channel[0].id for channel in channel_id_list]

        # Data split code
        len_const = 100 + len(str(channel_id))
        len_data = len(", ".join([str(ch) for ch in channel_id_list]))
        mean_len_data = len_data / len(channel_id_list)
        # len_const + len_data * ids_per_msg / mean_len_data = 1800
        ids_per_msg = int((1800 - len_const) / mean_len_data)

        data = []
        for i in range(0, len(channel_id_list), ids_per_msg):
            data.append(
                str(
                    encoder.JSONEncoder(allow_nan=False).encode(
                        {
                            channel_id: channel_id_list[i : i + ids_per_msg],
                        }
                    )
                )
            )
        for data_ in data:
            await (await ctx.bot.rest.fetch_channel(ctx.channel_id)).send(
                f"```\n{data_}\n```"
            )


def register(bot):
    pass
