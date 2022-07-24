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
from aiohttp import web

from . import cfg, custom_checks

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
    site = web.TCPSite(runner, "localhost", cfg.port)
    await site.start()


def register(bot: lightbulb.BotApp) -> None:
    # Arm all signals
    DailyResetSignal(bot).arm()
    WeeklyResetSignal(bot).arm()
    WeekendResetSignal(bot).arm()
    bot.listen(hikari.StartedEvent)(start_signal_receiver)

    # Connect commands
    bot.command(autopost_cmd_group)
