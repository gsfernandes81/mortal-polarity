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

import asyncio as aio
import datetime as dt
import sys
import typing as t

from atlas_provider_sqlalchemy.ddl import print_ddl
from sqlalchemy import VARCHAR, Boolean, DateTime, Integer
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import insert, select, update
from sqlalchemy.sql.schema import Column

from polarity import cfg, utils

Base = declarative_base()
db_engine = create_async_engine(
    cfg.db_url_async, connect_args=cfg.db_connect_args, **cfg.db_engine_args
)
db_session = sessionmaker(db_engine, **cfg.db_session_kwargs)


class LostSectorPostSettings(Base):
    __tablename__ = "lost_sector_post_settings"
    __mapper_args__ = {"eager_defaults": True}

    id = Column("id", Integer, primary_key=True)
    discord_autopost_enabled = Column(
        "discord_autopost_enabled",
        Boolean,
        default=True,
    )

    def __init__(
        self,
        id: int = 1,
        discord_autopost_enabled=False,
    ):
        self.id = id
        self.discord_autopost_enabled = discord_autopost_enabled

    @classmethod
    @utils.ensure_session(db_session)
    async def _get_enabled(cls, prop: str, id: int = 1, session: AsyncSession = None):
        enabled = (
            await session.execute(select(getattr(cls, prop)).where(cls.id == id))
        ).scalar()

        if enabled is None:
            self = cls(id=id)
            session.add(self)
            enabled = getattr(self, prop)

        return enabled

    @classmethod
    @utils.ensure_session(db_session)
    async def _set_enabled(
        cls, prop: str, enabled: bool, id: int = 1, session: AsyncSession = None
    ):
        await session.execute(update(cls).where(cls.id == id).values({prop: enabled}))

    @classmethod
    async def get_discord_enabled(cls, id: int = 1):
        return await cls._get_enabled("discord_autopost_enabled", id=id)

    @classmethod
    async def set_discord_enabled(cls, enabled: bool, id: int = 1):
        return await cls._set_enabled("discord_autopost_enabled", enabled, id=id)


class BungieCredentials(Base):
    __tablename__ = "bungie_credentials"
    __mapper_args__ = {"eager_defaults": True}

    id = Column("id", Integer, primary_key=True)
    api_key = cfg.bungie_api_key
    client_id = cfg.bungie_client_id
    client_secret = cfg.bungie_client_secret
    refresh_token = Column("refresh_token", VARCHAR(1024), default=None)
    refresh_token_expires = Column("refresh_token_expires", DateTime, default=None)

    def __init__(
        self,
        id: int = 1,
        refresh_token=None,
        refresh_token_expires=None,
    ):
        self.id = id
        self.refresh_token = refresh_token
        self.refresh_token_expires = refresh_token_expires

    @classmethod
    @utils.ensure_session(db_session)
    async def get_credentials(cls, id=1, session: AsyncSession = None) -> t.Self:
        return (await session.execute(select(cls).where(cls.id == id))).scalar()

    @classmethod
    @utils.ensure_session(db_session)
    async def set_refresh_token(
        cls,
        id=1,
        refresh_token=None,
        refresh_token_expires=None,
        session: AsyncSession = None,
    ):
        refresh_token_expires = dt.datetime.now() + dt.timedelta(
            seconds=refresh_token_expires * 0.8  # 20% Factor of Safety
        )

        self: cls = (await session.execute(select(cls.id).where(cls.id == id))).scalar()

        if self:
            await session.execute(
                update(cls)
                .where(cls.id == id)
                .values(
                    {
                        cls.refresh_token: refresh_token,
                        cls.refresh_token_expires: refresh_token_expires,
                    }
                )
            )
        else:
            await session.execute(
                insert(cls).values(
                    {
                        cls.id: id,
                        cls.refresh_token: refresh_token,
                        cls.refresh_token_expires: refresh_token_expires,
                    }
                )
            )


async def recreate_all():
    # db_engine = create_engine(cfg.db_url, connect_args=cfg.db_connect_args)
    db_engine = create_async_engine(cfg.db_url_async, connect_args=cfg.db_connect_args)
    # db_session = sessionmaker(db_engine, **cfg.db_session_kwargs)

    async with db_engine.begin() as conn:
        print(f"Dropping tables: {list(Base.metadata.tables.keys())}")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        print(f"Created tables: {list(Base.metadata.tables.keys())}")


if __name__ == "__main__":
    if "--print-ddl" in sys.argv:
        print_ddl("mysql", [Base])

    if "--recreate-all" in sys.argv:
        aio.run(recreate_all())
