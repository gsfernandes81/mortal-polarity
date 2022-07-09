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
from typing import Union

import hikari
import lightbulb
from aiohttp import web
from sqlalchemy import select, update

from . import cfg, custom_checks
from .user_commands import get_lost_sector_text
from .utils import _create_or_get
from .schemas import db_session
from .schemas import LostSectorPostSettings, LostSectorAutopostChannel

app = web.Application()


class BaseCustomEvent(hikari.Event):
    def __init__(self, bot) -> None:
        super().__init__()
        self.bot: lightbulb.BotApp = bot

    @property
    def app(self) -> lightbulb.BotApp:
        return self.bot


# Event that dispatches itself when a destiny 2 daily reset occurs.
# When a destiny 2 reset occurs, the reset_signaller.py process
# will send a signal to this process, which will be passed on
# as a hikari.Event that is dispatched bot-wide
class ResetSignal(BaseCustomEvent):
    qualifier: str

    def fire(self) -> None:
        self.bot.event_manager.dispatch(self)

    async def remote_fire(self, request: web.Request) -> web.Response:
        if str(request.remote) == "127.0.0.1":
            logging.info(
                "{self.qualifier} reset signal received and passed on".format(self=self)
            )
            self.fire()
            return web.Response(status=200)
        else:
            logging.warning(
                "{self.qualifier} reset signal received from non-local source, ignoring".format(
                    self=self
                )
            )
            return web.Response(status=401)

    def arm(self) -> None:
        # Run the hypercorn server to wait for the signal
        # This method is non-blocking
        app.add_routes(
            [
                web.post(
                    "/{self.qualifier}-reset-signal".format(self=self),
                    self.remote_fire,
                ),
            ]
        )


class DailyResetSignal(ResetSignal):
    qualifier = "daily"


class WeeklyResetSignal(ResetSignal):
    qualifier = "weekly"


class LostSectorSignal(BaseCustomEvent):
    def __init__(self, bot: lightbulb.BotApp, id: int = 0) -> None:
        super().__init__(bot)
        self.id = id
        self.bot = bot

    async def conditional_daily_reset_repeater(self, event: DailyResetSignal) -> None:
        if await self.is_autoannounce_enabled():
            event.bot.dispatch(self)

    async def is_autoannounce_enabled(self):
        settings = await _create_or_get(
            LostSectorPostSettings, 0, autoannounce_enabled=True
        )
        return settings.autoannounce_enabled

    def arm(self) -> None:
        self.bot.listen()(self.conditional_daily_reset_repeater)


async def lost_sector_announcer(event: LostSectorSignal):
    async with db_session() as session:
        async with session.begin():
            channel_id_list = (
                await session.execute(
                    select(LostSectorAutopostChannel).where(
                        LostSectorAutopostChannel.enabled == True
                    )
                )
            ).fetchall()
            channel_id_list = [] if channel_id_list is None else channel_id_list
            channel_id_list = [channel[0].id for channel in channel_id_list]

    logging.info("Announcing lost sectors to {} channels".format(len(channel_id_list)))
    start_time = dt.datetime.now()
    embed = await get_lost_sector_text()

    async def _send_embed_if_textable_channel(channel_id: int) -> None:
        try:
            channel = await event.bot.rest.fetch_channel(channel_id)
            # Can add hikari.GuildNewsChannel for announcement channel support
            # could be useful if we automate more stuff for Kyber
            if isinstance(channel, hikari.TextableChannel):
                await channel.send(embed=embed)
        except (hikari.ForbiddenError, hikari.NotFoundError):
            logging.warning(
                "Channel {} not found or not messageable, disabling lost sector posts".format(
                    channel_id
                )
            )
            async with db_session() as session:
                async with session.begin():
                    await session.execute(
                        update(LostSectorAutopostChannel)
                        .where(LostSectorAutopostChannel.id == channel_id)
                        .values(enabled=False)
                    )

    await asyncio.gather(
        *[_send_embed_if_textable_channel(channel_id) for channel_id in channel_id_list]
    )

    end_time = dt.datetime.now()
    time_delta = end_time - start_time
    minutes = time_delta.seconds // 60
    seconds = time_delta.seconds % 60
    logging.info(
        "Announcement completed in {} minutes and {} seconds".format(minutes, seconds)
    )


@lightbulb.add_checks(
    lightbulb.checks.dm_only
    | custom_checks.has_guild_permissions(hikari.Permissions.ADMINISTRATOR)
)
@lightbulb.command(
    "autopost", "Server autopost management, can be used by server administrators only"
)
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def autopost_cmd_group(ctx: lightbulb.Context) -> None:
    await ctx.respond(
        "Server autopost management commands, please use the subcommands here to manage autoposts"
    )


@autopost_cmd_group.child
@lightbulb.option(
    "option",
    "Enabled or disabled",
    type=str,
    choices=["Enable", "Disable"],
    required=True,
)
@lightbulb.command(
    "lostsector",
    "Lost sector auto posts",
    auto_defer=True,
    guilds=cfg.kyber_discord_server_id,
    inherit_checks=True,
)
@lightbulb.implements(lightbulb.SlashSubCommand)
async def lost_sector_auto(ctx: lightbulb.Context) -> None:
    channel_id: int = ctx.channel_id
    server_id: int = ctx.guild_id if ctx.guild_id is not None else -1
    option: bool = True if ctx.options.option.lower() == "enable" else False
    bot = ctx.bot
    if await _bot_has_message_perms(bot, channel_id):
        async with db_session() as session:
            async with session.begin():
                channel = await session.get(LostSectorAutopostChannel, channel_id)
                if channel is None:
                    channel = LostSectorAutopostChannel(channel_id, server_id, option)
                    session.add(channel)
                else:
                    channel.enabled = option
        await ctx.respond(
            "Lost sector autoposts {}".format("enabled" if option else "disabled")
        )
    else:
        await ctx.respond(
            'The bot does not have the "Send Messages" or the'
            + ' "Send Messages in Threads" permission here'
        )


@autopost_cmd_group.set_error_handler
async def announcements_error_handler(
    event: lightbulb.MissingRequiredPermission,
) -> None:
    ctx = event.context
    await ctx.respond(
        "You cannot change this setting because you "
        + 'do not have "Administrator" permissions in this server'
    )


def _wire_listeners(bot: lightbulb.BotApp) -> None:
    """Connects all listener coroutines to the bot"""
    for handler in [
        lost_sector_announcer,
    ]:
        bot.listen()(handler)


async def _bot_has_message_perms(
    bot: lightbulb.BotApp, channel: Union[hikari.TextableChannel, int]
) -> bool:
    if not isinstance(channel, hikari.TextableChannel):
        channel = await bot.rest.fetch_channel(channel)
    if isinstance(channel, hikari.TextableChannel):
        if isinstance(channel, hikari.TextableGuildChannel):
            guild = await channel.fetch_guild()
            self_member = await bot.rest.fetch_member(guild, bot.get_me())
            perms = lightbulb.utils.permissions_in(channel, self_member)
            # Check if we have the send messages permission in the channel
            # Refer to hikari.Permissions to see how / why this works
            # Note: Hikari doesn't recognize threads
            # Channel types 10, 11, 12 and 15 are thread types as specified in:
            # https://discord.com/developers/docs/resources/channel#channel-object-channel-types
            # If the channel is a thread, we need to check for the SEND_MESSAGES_IN_THREADS perm
            if channel.type in [10, 11, 12, 15]:
                return (
                    hikari.Permissions.SEND_MESSAGES_IN_THREADS & perms
                ) == hikari.Permissions.SEND_MESSAGES_IN_THREADS
            else:
                return (
                    hikari.Permissions.SEND_MESSAGES & perms
                ) == hikari.Permissions.SEND_MESSAGES
        else:
            return True


async def arm(bot: lightbulb.BotApp) -> None:
    # Arm all signals
    DailyResetSignal(bot).arm()
    WeeklyResetSignal(bot).arm()
    LostSectorSignal(bot).arm()
    # Connect listeners to the bot
    _wire_listeners(bot)
    # Connect commands
    bot.command(autopost_cmd_group)
    # Start the web server for periodic signals from apscheduler
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", cfg.port)
    await site.start()
