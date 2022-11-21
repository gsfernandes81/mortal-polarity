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
import functools
import logging
import re
from abc import ABC, abstractmethod
from typing import Type, Union

import hikari
import lightbulb
from aiohttp import web
from sqlalchemy import BigInteger, Boolean, Integer, select
from sqlalchemy.orm import declarative_mixin, declared_attr
from sqlalchemy.sql.schema import Column

from . import cfg, custom_checks
from .controller import kyber as control_cmd_group
from .utils import _send_embed, db_session, operation_timer

app = web.Application()

logger = logging.getLogger(__name__)


@declarative_mixin
class BasePostSettings:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    __mapper_args__ = {"eager_defaults": True}

    id = Column("id", Integer, primary_key=True)
    autoannounce_enabled = Column(
        "autoannounce_enabled", Boolean, default=True, server_default="t"
    )

    def __init__(self, id, autoannounce_enabled=True):
        self.id = id
        self.autoannounce_enabled = autoannounce_enabled

    async def get_announce_embed(self) -> hikari.Embed:
        pass


@declarative_mixin
class BaseChannelRecord:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    __mapper_args__ = {"eager_defaults": True}

    id = Column("id", BigInteger, primary_key=True)
    server_id = Column("server_id", BigInteger)
    last_msg_id = Column("last_msg_id", BigInteger)
    enabled = Column("enabled", Boolean)

    # Settings object for this channel type
    settings_records: Type[BasePostSettings]
    control_command_name: str = None
    # Follow channel for this announcement type
    follow_channel: int = None

    def __init__(self, id: int, server_id: int, enabled: bool):
        self.id = id
        self.server_id = server_id
        self.enabled = enabled

    @classmethod
    def register(
        cls,
        bot: lightbulb.BotApp,
        cmd_group: lightbulb.SlashCommandGroup,
        announce_event: Type[hikari.Event],
    ):
        cls.control_command_name = (
            " ".join(re.findall("[A-Z][^A-Z]*", cls.__name__)[:-2])
            if cls.control_command_name is None
            else cls.control_command_name
        )
        cmd_group.child(
            lightbulb.option(
                "option",
                "Enabled or disabled",
                type=str,
                choices=["Enable", "Disable"],
                required=True,
            )(
                lightbulb.command(
                    cls.control_command_name.lower().replace(" ", "_"),
                    "{} auto posts".format(cls.control_command_name.capitalize()),
                    auto_defer=True,
                    guilds=cfg.control_discord_server_id,
                    inherit_checks=True,
                )(
                    lightbulb.implements(lightbulb.SlashSubCommand)(
                        functools.partial(cls.autopost_ctrl_usr_cmd, cls)
                    )
                )
            )
        )
        bot.listen(announce_event)(cls.announcer)

    @staticmethod
    async def autopost_ctrl_usr_cmd(
        # Command for the user to be able to control autoposts in their server
        cls,
        ctx: lightbulb.Context,
    ) -> None:
        channel_id: int = ctx.channel_id
        server_id: int = ctx.guild_id if ctx.guild_id is not None else -1
        option: bool = True if ctx.options.option.lower() == "enable" else False
        bot = ctx.bot
        if await cls._check_bot_has_message_perms(bot, channel_id):
            async with db_session() as session:
                async with session.begin():
                    channel = await session.get(cls, channel_id)
                    if channel is None:
                        channel = cls(channel_id, server_id, option)
                        session.add(channel)
                    else:
                        channel.enabled = option
            await ctx.respond(
                " ".join(re.findall("[A-Z][^A-Z]*", cls.__name__)[:-2])
                + " autoposts {}".format("enabled" if option else "disabled")
            )
        else:
            await ctx.respond(
                'The bot does not have the "Send Messages" or the'
                + ' "Send Messages in Threads" permission here'
            )

    @staticmethod
    async def _check_bot_has_message_perms(
        bot: lightbulb.BotApp, channel: Union[hikari.TextableChannel, int]
    ) -> bool:
        if not isinstance(channel, hikari.TextableChannel):
            # Get channel from cache if possible
            channel = bot.cache.get_guild_channel(
                channel
            ) or await bot.rest.fetch_channel(channel)

        if isinstance(channel, hikari.TextableChannel):
            if isinstance(channel, hikari.TextableGuildChannel):
                guild = channel.get_guild() or await channel.fetch_guild()
                self_member = bot.cache.get_member(
                    guild, bot.get_me()
                ) or await bot.rest.fetch_member(guild, bot.get_me())
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

    @classmethod
    async def announcer(cls, event):
        async with db_session() as session:
            async with session.begin():
                settings: BasePostSettings = await session.get(cls.settings_records, 0)
            async with session.begin():
                channel_id_list = (
                    await session.execute(select(cls).where(cls.enabled == True))
                ).fetchall()
                channel_id_list = [] if channel_id_list is None else channel_id_list
                channel_id_list = [channel[0].id for channel in channel_id_list]

            logger.info(
                # Note, need to implement regex to specify which announcement
                # is being carried out in these logs
                "Announcing posts to {} channels".format(len(channel_id_list))
            )
            with operation_timer("Announce", logger):
                embed = await settings.get_announce_embed()
                try:
                    channel_id_list.remove(cls.follow_channel)
                except ValueError:
                    pass
                else:
                    channel_id_list.append(cls.follow_channel)
                finally:
                    exceptions = await asyncio.gather(
                        *[
                            _send_embed(channel_id, event, embed, cls, logger=logger)
                            for channel_id in channel_id_list[:-1]
                        ],
                        return_exceptions=True
                    )
                    # Run the last channel in list (Kyber's announce channel)
                    exceptions.extend(
                        await asyncio.gather(
                            *[
                                _send_embed(
                                    channel_id, event, embed, cls, logger=logger
                                )
                                for channel_id in channel_id_list[-1:]
                            ],
                            return_exceptions=True
                        )
                    )
                    for e in exceptions:
                        if e is not None:
                            logger.exception(e)


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
            logger.info(
                "{self.qualifier} reset signal received and passed on".format(self=self)
            )
            self.fire()
            return web.Response(status=200)
        else:
            logger.warning(
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


class WeekendResetSignal(ResetSignal):
    qualifier = "weekend"


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


@autopost_cmd_group.set_error_handler
async def announcements_error_handler(
    event: lightbulb.MissingRequiredPermission,
) -> None:
    ctx = event.context
    await ctx.respond(
        "You cannot change this setting because you "
        + 'do not have "Administrator" permissions in this server'
    )


async def start_signal_receiver(event: hikari.StartedEvent) -> None:
    # Start the web server for periodic signals from apscheduler
    runner = web.AppRunner(app)
    await runner.setup()
    # Switch to ipv4 since railway hosting does not like ipv6
    site = web.TCPSite(runner, "127.0.0.1", cfg.port)
    await site.start()


class AutopostsBase(ABC):
    def __init__(self):
        self.autopost_cmd_group = autopost_cmd_group
        self.control_cmd_group = control_cmd_group

    @abstractmethod
    def register(self, bot: lightbulb.BotApp) -> None:
        pass


class Autoposts(AutopostsBase):
    def register(self, bot: lightbulb.BotApp) -> None:
        DailyResetSignal(bot).arm()
        WeeklyResetSignal(bot).arm()
        WeekendResetSignal(bot).arm()
        bot.listen(hikari.StartedEvent)(start_signal_receiver)

        # Connect commands
        bot.command(self.autopost_cmd_group)


autoposts = Autoposts()
