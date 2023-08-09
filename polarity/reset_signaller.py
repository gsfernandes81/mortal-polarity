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

# This architecture for a periodic signal is used since
# apscheduler 3.x has quirks that make it difficult to
# work with in a single process with async without global state.
# These problems are expected to be solved by the release
# of apscheduler 4.x which will have a better async support
# This architecture uses aiohttps requests to a quart (async flask)
# server to send a signal from the scheduler to the reciever.
# The relevant tracking issue for apscheduler 4.x is:
# https://github.com/agronholm/apscheduler/issues/465

import asyncio
import datetime as dt

import aiohttp
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import utc

from . import cfg

# Port for main.py / the "main" process to run on
# This will be 100 less than the Port variable (see Honcho docs)
PORT = cfg.port - 100

# We use the AsyncIOScheduler since the discord client library
# runs mostly asynchronously
# This will be useful when this is run in a single process
# when apscheduler 4.x is released
_scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=cfg.legacy_db_url)},
    job_defaults={
        "coalesce": "true",
        "misfire_grace_time": 1800,
        "max_instances": 1,
    },
)


async def remote_daily_reset():
    print("Sending daily reset signal")
    async with aiohttp.ClientSession() as session:
        await session.post(
            "http://127.0.0.1:{}/daily-reset-signal".format(PORT), verify_ssl=False
        )


# This needs to be called at release
def add_remote_announce():
    # (Re)Add the scheduled job that signals destiny 2 reset

    test_time = dt.datetime.now() + dt.timedelta(minutes=2)
    test_cron_dict = {
        "year": test_time.year,
        "month": test_time.month,
        "day": test_time.day,
        "hour": test_time.hour,
        "minute": test_time.minute,
    }

    _scheduler.add_job(
        remote_daily_reset,
        CronTrigger(
            hour=17,
            timezone=utc,
        )
        if not cfg.test_env
        else CronTrigger(**test_cron_dict),
        replace_existing=True,
        id="0",
    )

    # Start up then shut down the scheduler to commit changes to the DB
    _scheduler.start(paused=True)
    _scheduler.shutdown(wait=True)


def start():
    """Blocking function to start the scheduler"""
    _scheduler.start()
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    start()
