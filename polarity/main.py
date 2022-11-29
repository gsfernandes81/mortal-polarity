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
import lightbulb as lb
import uvloop
from lightbulb.ext import tasks

from . import cfg, controller, migration_commands, user_commands
from .autopost import autoposts
from .ls import lost_sectors
from .weekly_reset import weekly_reset
from .xur import xur

uvloop.install()
bot: lb.BotApp = lb.BotApp(**cfg.lightbulb_params)

logger = logging.getLogger(__name__)


@tasks.task(m=30, auto_start=True, wait_before_execution=False)
async def autoupdate_status():
    if not bot.d.has_lb_started:
        await bot.wait_for(lb.events.LightbulbStartedEvent, timeout=None)
        bot.d.has_lightbulb_started = True

    await bot.update_presence(
        activity=h.Activity(
            name="{} servers : )".format(len(await bot.rest.fetch_my_guilds())),
            type=h.ActivityType.LISTENING,
        )
    )


if __name__ == "__main__":
    logger.info("Listening on port number {}".format(cfg.port))
    autoposts.register(bot)
    controller.register(bot)
    lost_sectors.register(bot)
    user_commands.register(bot)
    weekly_reset.register(bot)
    xur.register(bot)
    tasks.load(bot)
    migration_commands.register_all(bot)
    bot.run()
