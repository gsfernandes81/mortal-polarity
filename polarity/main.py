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

import hikari
import lightbulb
import uvloop

from . import cfg, controller, debug_commands, user_commands
from .autoannounce import arm
from .utils import Base

uvloop.install()
bot: lightbulb.BotApp = lightbulb.BotApp(**cfg.lightbulb_params)


@bot.listen(hikari.StartedEvent)
async def on_ready(event: hikari.StartedEvent) -> None:
    await arm(bot)


if __name__ == "__main__":
    user_commands.register_all(bot)
    controller.register_all(bot)
    if cfg.test_env:
        debug_commands.register_all(bot)
    bot.run()
