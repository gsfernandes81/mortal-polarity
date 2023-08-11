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
import typing as t

import aiocron
import hikari as h
import lightbulb as lb
from aiohttp import web
from hmessage import HMessage
from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import declarative_mixin, declared_attr
from sqlalchemy.sql.schema import Column

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


class BaseCustomEvent(h.Event):
    @classmethod
    def register(cls, bot: lb.BotApp) -> t.Self:
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


class DailyResetSignal(ResetSignal):
    qualifier = "daily"


async def on_start_schedule_signals(event: lb.LightbulbStartedEvent):
    # Run every day at 17:00 UTC
    @aiocron.crontab("0 17 * * *", start=True)
    # Use below crontab for testing
    # @aiocron.crontab("* * * * *", start=True)
    async def autopost_ls():
        DailyResetSignal.dispatch_with(bot=event.app)


def register(bot: lb.BotApp) -> None:
    DailyResetSignal.register(bot)
    bot.listen(lb.LightbulbStartedEvent)(on_start_schedule_signals)
