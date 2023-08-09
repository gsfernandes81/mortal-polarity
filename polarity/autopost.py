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
from typing import Type

import hikari as h
import lightbulb as lb
from aiohttp import web
from hmessage import HMessage
from sqlalchemy import BigInteger, Boolean, Integer, select
from sqlalchemy.orm import declarative_mixin, declared_attr
from sqlalchemy.sql.schema import Column

from . import cfg
from .utils import (
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
    # Follow channel for this announcement type
    follow_channel: int = None
    # Name displayed to user for this type of autopost
    # Must be plural and end with autoposts
    autopost_friendly_name: str = None

    def __init__(self, id: int, server_id: int, enabled: bool):
        self.id = id
        self.server_id = server_id
        self.enabled = enabled


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


async def start_signal_receiver(event: h.StartedEvent) -> None:
    # Start the web server for periodic signals from apscheduler
    runner = web.AppRunner(app)
    await runner.setup()
    # Switch to ipv4 since railway hosting does not like ipv6
    site = web.TCPSite(runner, "127.0.0.1", cfg.port)
    await site.start()


def register(bot: lb.BotApp) -> None:
    DailyResetSignal.register(bot).arm()
    bot.listen(h.StartedEvent)(start_signal_receiver)
