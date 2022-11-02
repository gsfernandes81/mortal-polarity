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

import logging
import hikari as h
import lightbulb
from sqlalchemy import select
import toolbox

from . import cfg, ls, weekly_reset, xur
from .utils import db_session


@lightbulb.command(
    name="migratability",
    description="Check how many bot follows can be moved to discord follows",
    guilds=(cfg.control_discord_server_id,),
    auto_defer=True,
)
@lightbulb.implements(lightbulb.SlashCommand)
async def migratability(ctx: lightbulb.Context) -> None:
    bot = ctx.bot

    await ctx.respond(content="Working...")

    embed = h.Embed(
        title="Migratability measure",
        description="Proportion of channels migratable to the new follow system\n",
        color=h.Color.from_hex_code("#a96eca"),
    )
    for channel_type, channel_record in [
        ("LS", ls.LostSectorAutopostChannel),
        ("Xur", xur.XurAutopostChannel),
        ("Reset", weekly_reset.WeeklyResetAutopostChannel),
    ]:

        async with db_session() as session:
            async with session.begin():
                channel_id_list = (
                    await session.execute(
                        select(channel_record).where(channel_record.enabled == True)
                    )
                ).fetchall()
                channel_id_list = [] if channel_id_list is None else channel_id_list
                channel_id_list = [channel[0].id for channel in channel_id_list]

        bot_user = bot.get_me()
        no_of_channels = len(channel_id_list)
        no_of_channels_w_perms = 0
        no_of_non_guild_channels = 0
        for channel_id in channel_id_list:

            channel = bot.cache.get_guild_channel(
                channel_id
            ) or await bot.rest.fetch_channel(channel_id)

            if not isinstance(channel, h.TextableGuildChannel):
                no_of_non_guild_channels += 1
                continue

            server_id = channel.guild_id
            guild: h.Guild = bot.cache.get_guild(
                server_id
            ) or await bot.rest.fetch_guild(server_id)

            bot_member = await bot.rest.fetch_member(guild, bot_user)
            perms = toolbox.calculate_permissions(bot_member, channel)
            logging.info(
                "Guild/Channel : {}/{}".format(channel.get_guild().name, channel.name)
            )

            if h.Permissions.MANAGE_WEBHOOKS in perms:
                no_of_channels_w_perms += 1

            embed.add_field(
                channel_type,
                "({} Migratable + {} Not Applicable) / {} Total".format(
                    no_of_channels_w_perms, no_of_non_guild_channels, no_of_channels
                ),
                inline=False,
            )

    await ctx.edit_last_response(embed=embed)


def register_all(bot: lightbulb.BotApp) -> None:
    for command in [
        migratability,
    ]:
        bot.command(command)
