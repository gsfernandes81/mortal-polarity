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
import miru as m
import uvloop
from lightbulb.ext import tasks

from . import cfg, controller, embeds, posts
from .autopost import autoposts
from .ls import lost_sectors
from .weekly_reset import weekly_reset
from .xur import xur

uvloop.install()
bot: lb.BotApp = lb.BotApp(**cfg.lightbulb_params)

logger = logging.getLogger(__name__)


async def update_status(guild_count: int):
    await bot.update_presence(
        activity=h.Activity(
            name="{} servers : )".format(guild_count),
            type=h.ActivityType.LISTENING,
        )
    )


@bot.listen()
async def on_start(event: lb.events.LightbulbStartedEvent):
    bot.d.guild_count = len(await bot.rest.fetch_my_guilds())
    await update_status(bot.d.guild_count)


@bot.listen()
async def on_guild_add(event: h.events.GuildJoinEvent):
    bot.d.guild_count += 1
    await update_status(bot.d.guild_count)


@bot.listen()
async def on_guild_rm(event: h.events.GuildLeaveEvent):
    bot.d.guild_count -= 1
    await update_status(bot.d.guild_count)


if __name__ == "__main__":
    logger.info("Listening on port number {}".format(cfg.port))
    m.install(bot)
    autoposts.register(bot)
    controller.register(bot)
    lost_sectors.register(bot)
    weekly_reset.register(bot)
    xur.register(bot)
    embeds.register(bot)
    posts.register(bot)
    tasks.load(bot)
    bot.run()
