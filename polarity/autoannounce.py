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
import hikari
import lightbulb
from hypercorn.asyncio import serve
from hypercorn.config import Config
import quart
from quart import request, jsonify
import asyncio

from . import cfg

config = Config()
config.bind = ["0.0.0.0:{}".format(cfg.port)]
app = quart.Quart(__name__)


# Event that dispatches itself when a destiny 2 daily reset occurs.
# When a destiny 2 reset occurs, the reset_signaller.py process
# will send a signal to this process, which will be passed on
# as a hikari.Event that is dispatched bot-wide
class ResetSignal(hikari.Event):
    qualifier: str

    def __init__(self, bot) -> None:
        super().__init__()
        self.bot: lightbulb.BotApp = bot

    @property
    def app(self) -> lightbulb.BotApp:
        return self.bot

    def fire(self) -> None:
        self.bot.event_manager.dispatch(self)

    def remote_fire(self) -> quart.Response:
        if str(request.remote_addr) == ("127.0.0.1"):
            logging.info(
                "{self.qualifier} reset signal received and passed on".format(self=self)
            )
            self.fire()
            return jsonify(success=True)
        else:
            logging.warning(
                "{self.qualifier} reset signal received from non-local source, ignoring".format(
                    self=self
                )
            )
            return jsonify(success=False)

    def arm(self) -> None:
        # Run the hypercorn server to wait for the signal
        # This method is non-blocking
        app.add_url_rule(
            "/{self.qualifier}-reset-signal".format(self=self),
            methods=[
                "POST",
            ],
            view_func=self.remote_fire,
            endpoint="{self.qualifier}-reset-signal".format(self=self),
        )


class DailyResetSignal(ResetSignal):
    qualifier = "daily"


class WeeklyResetSignal(ResetSignal):
    qualifier = "weekly"


async def arm(bot) -> None:
    DailyResetSignal(bot).arm()
    WeeklyResetSignal(bot).arm()
    asyncio.create_task(
        serve(
            app,
            config,
        )
    )
