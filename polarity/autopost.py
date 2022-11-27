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
from typing import Type, Union, List

import hikari as h
import lightbulb as lb
from aiohttp import web
from sqlalchemy import BigInteger, Boolean, Integer, select
from sqlalchemy.orm import declarative_mixin, declared_attr
from sqlalchemy.sql.schema import Column

from . import cfg, custom_checks
from .controller import kyber as control_cmd_group
from .utils import (
    send_message,
    db_session,
    operation_timer,
    _component_for_migration,
    _embed_for_migration,
    MessageFailureError,
    alert_owner,
)

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

    async def get_announce_embed(self) -> h.Embed:
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
    # Name displayed to user for this type of autopost
    # Must be plural and end with autoposts
    autopost_friendly_name: str = None

    def __init__(self, id: int, server_id: int, enabled: bool):
        self.id = id
        self.server_id = server_id
        self.enabled = enabled

    @classmethod
    def register(
        cls,
        bot: lb.BotApp,
        cmd_group: lb.SlashCommandGroup,
        announce_event: Type[h.Event],
    ):
        cls.control_command_name = (
            " ".join(re.findall("[A-Z][^A-Z]*", cls.__name__)[:-2])
            if cls.control_command_name is None
            else cls.control_command_name
        )
        cmd_group.child(
            lb.app_command_permissions(dm_enabled=False)(
                lb.option(
                    "option",
                    "Enabled or disabled",
                    type=str,
                    choices=["Enable", "Disable"],
                    required=True,
                )(
                    lb.command(
                        cls.control_command_name.lower().replace(" ", "_"),
                        "{} auto posts".format(cls.control_command_name.capitalize()),
                        auto_defer=True,
                        guilds=cfg.control_discord_server_id,
                        inherit_checks=True,
                    )(
                        lb.implements(lb.SlashSubCommand)(
                            functools.partial(cls.autopost_ctrl_usr_cmd, cls)
                        )
                    )
                )
            )
        )

        bot.listen(announce_event)(cls.announcer)

    @staticmethod
    async def autopost_ctrl_usr_cmd(
        # Command for the user to be able to control autoposts in their server
        cls,
        ctx: lb.Context,
    ) -> None:
        channel_id: int = ctx.channel_id
        server_id: int = ctx.guild_id if ctx.guild_id is not None else -1
        option: bool = True if ctx.options.option.lower() == "enable" else False
        bot = ctx.bot

        try:
            if option:
                # Fetch all follow based webhooks that have our channel as a source
                follow_webhooks = [
                    hook
                    for hook in await bot.rest.fetch_channel_webhooks(channel_id)
                    if isinstance(hook, h.ChannelFollowerWebhook)
                    and hook.source_channel.id == cls.follow_channel
                ]
                if len(follow_webhooks) == 0:
                    await bot.rest.follow_channel(cls.follow_channel, channel_id)
                    await ctx.respond("{} enabled".format(cls.autopost_friendly_name))
                else:
                    await ctx.respond(
                        "{} were already enabled".format(cls.autopost_friendly_name)
                    )
            else:
                # Fetch all follow based webhooks that have our channel as a source
                follow_webhooks = [
                    hook
                    for hook in await bot.rest.fetch_channel_webhooks(channel_id)
                    if isinstance(hook, h.ChannelFollowerWebhook)
                    and hook.source_channel.id == cls.follow_channel
                ]
                if len(follow_webhooks) == 0:
                    await ctx.respond(
                        "{} were already disabled.".format(cls.autopost_friendly_name)
                    )
                else:
                    [await bot.rest.delete_webhook(hook) for hook in follow_webhooks]
                    await ctx.respond("{} disabled".format(cls.autopost_friendly_name))

        except h.ForbiddenError:
            owner = await bot.rest.fetch_user((await bot.fetch_owner_ids())[0])
            await ctx.respond(
                (
                    'The bot does not have the "Manage Webhooks" permission here. '
                    + "Please reinvite the bot with the below button "
                    + "or contact {}#{} for assistance"
                ).format(owner.username, owner.discriminator),
                components=_component_for_migration(bot),
            )
        except Exception as e:
            owner = await bot.rest.fetch_user((await bot.fetch_owner_ids())[0])
            await ctx.respond(
                "An unrecognized error has occured, please message {}#{}".format(
                    owner.username, owner.discriminator
                )
            )
            logger.exception(e)
            await alert_owner(
                "An autopost follow command for\nchannel id:",
                channel_id,
                "\nserver id:",
                server_id,
                "\nhas failed with exception:",
                e,
                bot=bot,
                mention_mods=True,
                channel=cfg.alerts_channel_id,
            )

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
                channel_record_list = [channel[0] for channel in channel_id_list]
                channel_id_list = [channel[0].id for channel in channel_id_list]

            logger.info(
                # Note, need to implement regex to specify which announcement
                # is being carried out in these logs
                "Announcing posts to {} channels".format(len(channel_id_list))
            )
            with operation_timer("Announce", logger):
                embed = await settings.get_announce_embed()
                channel_id_list.remove(cls.follow_channel)
                exceptions: List[
                    Union[None, MessageFailureError]
                ] = await asyncio.gather(
                    *(
                        [
                            send_message(
                                event.app,
                                cls.follow_channel,
                                message_kwargs={"embed": embed},
                                crosspost=True,
                            )
                        ]
                        + [
                            send_message(
                                event.app,
                                channel_id,
                                message_kwargs={
                                    "embed": _embed_for_migration(embed),
                                    "components": _component_for_migration(event.app),
                                },
                            )
                            for channel_id in channel_id_list
                        ]
                    ),
                    return_exceptions=True
                )

                for e in exceptions:
                    if e is not None:
                        channel_record = (
                            await session.execute(
                                select(cls).where(cls.id == e.channel_id)
                            )
                        ).fetchall()[0][0]
                        if cfg.disable_bad_channels:
                            channel_record.enabled = False
                        logger.exception(e)


class BaseCustomEvent(h.Event):
    @classmethod
    def register(cls, bot: lb.BotApp) -> h.Event:
        """Instantiate the event and set the .app property to the specified bot"""
        self = cls()
        self._app = bot
        return self

    def dispatch(self):
        """Sends out the registered event.

        .register must be called before using this
        ie this must be on a correctly instantiated event object"""
        self.app.event_manager.dispatch(self)

    @classmethod
    def dispatch_with(cls, *, bot: lb.BotApp):
        """Shortcut method to .register(bot=bot).dispatch()"""
        cls.register(bot).dispatch()

    @property
    def app(self) -> lb.BotApp:
        """Property that returns the bot this event is registered with"""
        return self._app


# Event that dispatches itself when a destiny 2 daily reset occurs.
# When a destiny 2 reset occurs, the reset_signaller.py process
# will send a signal to this process, which will be passed on
# as a h.Event that is dispatched bot-wide
class ResetSignal(BaseCustomEvent):
    qualifier: str

    async def remote_dispatch(self, request: web.Request) -> web.Response:
        """Function to be called when converting a http post -> a dispatched bot signal

        This function checks that the call was from localhost and then fires the signal
        Returns an aiohttp response (either 200: Success or 401)"""
        if str(request.remote) == "127.0.0.1":
            logger.info(
                "{self.qualifier} reset signal received and passed on".format(self=self)
            )
            self.dispatch()
            return web.Response(status=200)
        else:
            logger.warning(
                "{self.qualifier} reset signal received from non-local source, ignoring".format(
                    self=self
                )
            )
            return web.Response(status=401)

    def arm(self) -> None:
        """Adds the route for this signal to the aiohttp routes table

        Must be called for aiohttp to dispatch bot signals on http signal receipt"""
        app.add_routes(
            [
                web.post(
                    "/{self.qualifier}-reset-signal".format(self=self),
                    self.remote_dispatch,
                ),
            ]
        )


class DailyResetSignal(ResetSignal):
    qualifier = "daily"


class WeeklyResetSignal(ResetSignal):
    qualifier = "weekly"


class WeekendResetSignal(ResetSignal):
    qualifier = "weekend"


@lb.add_checks(
    custom_checks.has_guild_permissions(h.Permissions.MANAGE_WEBHOOKS)
    | custom_checks.has_guild_permissions(h.Permissions.ADMINISTRATOR)
)
@lb.command(
    "autopost", "Server autopost management, can be used by server administrators only"
)
@lb.implements(lb.SlashCommandGroup)
async def autopost_cmd_group(ctx: lb.Context) -> None:
    await ctx.respond(
        "Server autopost management commands, please use the subcommands here to manage autoposts"
    )


@autopost_cmd_group.set_error_handler
async def announcements_error_handler(
    event: lb.MissingRequiredPermission,
) -> None:
    ctx = event.context
    await ctx.respond(
        "You cannot change this setting because you "
        + "do not have Administrator or Manage Webhooks "
        + "permissions in this server"
    )


async def start_signal_receiver(event: h.StartedEvent) -> None:
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
    def register(self, bot: lb.BotApp) -> None:
        pass


class Autoposts(AutopostsBase):
    def register(self, bot: lb.BotApp) -> None:
        DailyResetSignal.register(bot).arm()
        WeeklyResetSignal.register(bot).arm()
        WeekendResetSignal.register(bot).arm()
        bot.listen(h.StartedEvent)(start_signal_receiver)

        # Connect commands
        bot.command(self.autopost_cmd_group)


autoposts = Autoposts()
