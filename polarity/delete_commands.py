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

# RUN WITH CAUTION
# DELETES ALL PUBLISHED COMMANDS FOR cfg.main_token GLOBALLY
import asyncio

import hikari as h

from . import cfg

rest = h.RESTApp()

TOKEN = cfg.discord_token


async def main():
    async with rest.acquire(cfg.discord_token, h.TokenType.BOT) as client:
        application = await client.fetch_application()

        await client.set_application_commands(application.id, (), guild=h.UNDEFINED)

        await client.set_application_commands(
            application.id, (), guild=(cfg.kyber_discord_server_id)
        )

        await client.set_application_commands(
            application.id, (), guild=(cfg.control_discord_server_id)
        )


if __name__ == "__main__":
    asyncio.run(main())
