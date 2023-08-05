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

import functools
import logging
import re
from abc import ABC, abstractmethod
from typing import Type

import hikari as h
import lightbulb as lb
from aiohttp import web
from hmessage import HMessage
from sqlalchemy import BigInteger, Boolean, Integer, select
from sqlalchemy.orm import declarative_mixin, declared_attr
from sqlalchemy.sql.schema import Column

from . import cfg, custom_checks
from .controller import kyber as control_cmd_group
from .utils import (
    _components_for_migration,
    alert_owner,
    db_session,
    send_message,
    followable_name,
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

    async def get_announce_message(self) -> HMessage:
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
            # Only fetch channel as opposed to getting it from cache
            # since we want to make sure the bot can see the channel
            # when following it
            channel = await bot.rest.fetch_channel(channel_id)
        except h.ForbiddenError:
            await ctx.respond(
                'The bot does not have the "View Channel" permission here. '
                + "Please allow the bot to see this channel to enable "
                + "autoposts here"
            )
            return

        try:
            if option:
                try:
                    # Fetch all follow based webhooks that have our channel as a source
                    follow_webhooks = [
                        hook
                        for hook in await bot.rest.fetch_channel_webhooks(channel)
                        if isinstance(hook, h.ChannelFollowerWebhook)
                        and hook.source_channel.id == cls.follow_channel
                    ]
                except KeyError:
                    # For some webhook types the source channel parameter does not
                    # deserialise on hikari's end correctly
                    follow_webhooks = []

                if len(follow_webhooks) == 0:
                    await bot.rest.follow_channel(cls.follow_channel, channel)
                    await ctx.respond("{} enabled".format(cls.autopost_friendly_name))
                else:
                    await ctx.respond(
                        "{} were already enabled".format(cls.autopost_friendly_name)
                    )
            else:
                try:
                    # Fetch all follow based webhooks that have our channel as a source
                    follow_webhooks = [
                        hook
                        for hook in await bot.rest.fetch_channel_webhooks(channel)
                        if isinstance(hook, h.ChannelFollowerWebhook)
                        and hook.source_channel.id == cls.follow_channel
                    ]
                except KeyError:
                    # For some webhook types the source channel parameter does not
                    # deserialise on hikari's end correctly
                    follow_webhooks = []

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
                    'The bot does not seem to have the "Manage Webhooks" permission '
                    + "here. Please reinvite the bot with the below button."
                    + "or contact @{} for assistance"
                ).format(owner.username),
                components=_components_for_migration(bot),
            )
        except h.BadRequestError as e:
            owner = await bot.rest.fetch_user((await bot.fetch_owner_ids())[0])
            await ctx.respond(
                "You cannot enable autoposts in an announcement channels "
                + "or this channel type. please message @{} for assistance".format(
                    owner.username
                ),
            )
            logger.exception(e)
        except Exception as e:
            owner = await bot.rest.fetch_user((await bot.fetch_owner_ids())[0])
            await ctx.respond(
                "An unrecognized error has occured, please message {}".format(
                    owner.username
                )
            )
            logger.exception(e)
            await alert_owner(
                "An autopost follow command for\nchannel id:",
                channel,
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
        await cls._announcer(event)

    @classmethod
    async def _announcer(cls, event, **kwargs):
        async with db_session() as session:
            async with session.begin():
                settings: BasePostSettings = await session.get(cls.settings_records, 0)

                followable_name_ = followable_name(id=cls.follow_channel)

                logger.info("Announcing posts to channel {}".format(followable_name_))
                message = await settings.get_announce_message(**kwargs)

                try:
                    message = await send_message(
                        event.app,
                        cls.follow_channel,
                        message_kwargs=message.to_message_kwargs(),
                    )
                except Exception as e:
                    logger.exception(e)
                else:
                    channel_record = await session.get(cls, cls.follow_channel)
                    channel_record.last_msg_id = message.id


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
    | lb.checks.owner_only
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
