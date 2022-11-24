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

import asyncio
import datetime as dt
import logging

import hikari as h
import lightbulb as lb
import toolbox
from sqlalchemy import select

from . import cfg, ls, weekly_reset, xur
from .utils import FeatureDisabledError, db_session, operation_timer

logger = logging.getLogger(__name__)


@lb.add_checks(lb.checks.has_roles(cfg.admin_role))
@lb.command(
    name="migratability",
    description="Check how many bot follows can be moved to discord follows",
    guilds=(cfg.control_discord_server_id,),
    auto_defer=True,
)
@lb.implements(lb.SlashCommand)
async def migratability(ctx: lb.Context) -> None:
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
        no_not_found = 0
        for channel_id in channel_id_list:

            try:
                channel = bot.cache.get_guild_channel(
                    channel_id
                ) or await bot.rest.fetch_channel(channel_id)
            except (h.errors.NotFoundError, h.errors.ForbiddenError):
                no_not_found += 1
                continue

            if not isinstance(channel, h.TextableGuildChannel):
                no_of_non_guild_channels += 1
                continue

            server_id = channel.guild_id
            guild: h.Guild = bot.cache.get_guild(
                server_id
            ) or await bot.rest.fetch_guild(server_id)

            bot_member = await bot.rest.fetch_member(guild, bot_user)
            perms = toolbox.calculate_permissions(bot_member, channel)

            if h.Permissions.MANAGE_WEBHOOKS in perms:
                no_of_channels_w_perms += 1

        embed.add_field(
            channel_type,
            "({} Migratable + {} Not Applicable + {} Not Found) / {} Total".format(
                no_of_channels_w_perms,
                no_of_non_guild_channels,
                no_not_found,
                no_of_channels,
            ),
            inline=False,
        )

    await ctx.edit_last_response(content="", embed=embed)


@lb.add_checks(lb.checks.has_roles(cfg.admin_role))
@lb.option(
    name="channel",
    description="Which announce channel to migrate",
    choices=["ls", "xur", "reset"],
)
@lb.command(
    name="migrate",
    description="Move to the new system",
    guilds=(cfg.control_discord_server_id,),
    auto_defer=True,
)
@lb.implements(lb.SlashCommand)
async def migrate(ctx: lb.Context):
    bot: lb.BotApp = ctx.bot

    if ctx.options.channel == "ls":
        follow_channel = cfg.ls_follow_channel_id
        channel_table = ls.LostSectorAutopostChannel
    elif ctx.options.channel == "xur":
        follow_channel = cfg.xur_follow_channel_id
        channel_table = xur.XurAutopostChannel
    elif ctx.options.channel == "reset":
        follow_channel = cfg.reset_follow_channel_id
        channel_table = weekly_reset.WeeklyResetAutopostChannel

    async with db_session() as session:
        async with session.begin():
            channel_record_list = (
                await session.execute(
                    select(channel_table).where(channel_table.enabled == True)
                )
            ).fetchall()
            channel_record_list = (
                [] if channel_record_list is None else channel_record_list
            )
            channel_record_list = [channel[0] for channel in channel_record_list]

            not_found = 0
            forbidden = 0
            bad_request = 0
            not_guild = 0
            iterations = 0

            await ctx.respond(
                content="Migrating {} channels\n".format(len(channel_record_list))
            )
            await asyncio.sleep(3)

            with operation_timer("Migrate") as time_till:
                for channel_record in channel_record_list:
                    try:
                        channel = bot.cache.get_guild_channel(
                            channel_record.id
                        ) or await bot.rest.fetch_channel(channel_record.id)

                        # Will throw an attribute error if not a guild channel:
                        channel.guild_id

                        if channel_record.server_id == cfg.kyber_discord_server_id:
                            continue

                        if follow_channel < 0:
                            raise FeatureDisabledError(
                                "Following channels is disabled!"
                            )

                        if not follow_channel in [
                            webhook.source_channel.id
                            for webhook in await bot.rest.fetch_channel_webhooks(
                                channel
                            )
                            if isinstance(webhook, h.ChannelFollowerWebhook)
                        ]:
                            await bot.rest.follow_channel(follow_channel, channel)

                    except FeatureDisabledError as e:
                        logger.exception(e)
                    except h.BadRequestError:
                        bad_request += 1
                    except h.ForbiddenError:
                        forbidden += 1
                    except h.NotFoundError:
                        not_found += 1
                    except AttributeError:
                        not_guild += 1
                    else:
                        channel_record.enabled = False
                        session.add(channel_record)
                    finally:
                        iterations += 1
                        rate = time_till(dt.datetime.now()) / iterations
                        if iterations % round(10 / rate) == 0 or iterations >= len(
                            channel_record_list
                        ):
                            summary = (
                                "**Operation progress / summary**\n"
                                + "{} bad requests\n".format(bad_request)
                                + "{} forbidden\n".format(forbidden)
                                + "{} not found\n".format(not_found)
                                + "{} not in a guild\n".format(not_guild)
                                + "{} total".format(iterations)
                            )
                            if iterations >= len(channel_record_list):
                                summary += "\n**Operation complete**"
                            await ctx.edit_last_response(content=summary)


def register_all(bot: lb.BotApp) -> None:
    for command in [
        migratability,
        migrate,
    ]:
        bot.command(command)
