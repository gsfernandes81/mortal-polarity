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

from abc import ABC, abstractclassmethod, abstractmethod, abstractstaticmethod

import hikari
from sqlalchemy import false
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.expression import delete, select

from . import cfg
from .schemas import Commands

db_engine = create_async_engine(cfg.db_url_async)
db_session = sessionmaker(db_engine, **cfg.db_session_kwargs)

bot = hikari.GatewayBot(token=cfg.main_token)


COMMAND_GUILD_ID = cfg.test_env if cfg.test_env else hikari.UNDEFINED


class CommandImpl(ABC):
    @abstractstaticmethod
    async def slash_builder() -> list:
        pass

    @abstractclassmethod
    async def handler(cls, event: hikari.Event):
        pass

    @abstractstaticmethod
    async def is_matching_command(event: hikari.Event) -> bool:
        pass


class add_command(CommandImpl):
    @staticmethod
    async def slash_builder() -> list:
        return [
            bot.rest.slash_command_builder(
                # ToDo: Add permission checks
                "add",
                "Add a link to the bot, only usable by Kyber et al",
            )
            .add_option(
                hikari.CommandOption(
                    type=hikari.OptionType.STRING,
                    name="name",
                    is_required=True,
                    description="Name of the link to add",
                )
            )
            .add_option(
                hikari.CommandOption(
                    type=hikari.OptionType.STRING,
                    name="description",
                    is_required=True,
                    description="Description of what is in this link and commmand",
                )
            )
            .add_option(
                hikari.CommandOption(
                    type=hikari.OptionType.STRING,
                    name="link",
                    is_required=True,
                    description="Link to post when this command is used",
                )
            ),
        ]

    @classmethod
    async def handler(cls, event: hikari.Event):
        options = event.interaction.options

        # Sort the options into a dict
        options_dict = {}
        for option in options:
            options_dict[option.name] = option.value

        async with db_session() as session:
            async with session.begin():
                additional_commands = (
                    await session.execute(select(Commands))
                ).fetchall()
                additional_commands = (
                    [] if additional_commands is None else additional_commands
                )
                additional_commands = [
                    command[0].name
                    for command in (await session.execute(select(Commands))).fetchall()
                ]
                if (
                    options_dict["name"]
                    in ["add", "edit", "remove"] + additional_commands
                ):
                    await event.interaction.edit_initial_response(
                        "A command with that name already exists"
                    )
                    return

                command = Commands(
                    options_dict["name"].lower(),
                    options_dict["description"],
                    options_dict["link"],
                )
                session.add(command)

        await register_commands()
        await event.interaction.edit_initial_response("Command added")
        return

    async def is_matching_command(event):
        return event.interaction.command_name == "add"


class user_command(CommandImpl):
    @staticmethod
    async def slash_builder():
        async with db_session() as session:
            async with session.begin():
                command_list = (await session.execute(select(Commands))).fetchall()
                command_list = [] if command_list is None else command_list
                return [
                    bot.rest.slash_command_builder(
                        command[0].name, command[0].description
                    )
                    for command in command_list
                ]

    @classmethod
    async def handler(cls, event: hikari.Event):
        async with db_session() as session:
            async with session.begin():
                matching_command = (
                    await session.execute(
                        select(Commands).where(
                            Commands.name == event.interaction.command_name
                        )
                    )
                ).fetchone()
                command_text_response = matching_command[0].text
                await event.interaction.edit_initial_response(
                    command_text_response,
                )
                return

    @staticmethod
    async def is_matching_command(event):
        async with db_session() as session:
            async with session.begin():
                matching_command = (
                    await session.execute(
                        select(Commands).where(
                            Commands.name == event.interaction.command_name
                        )
                    )
                ).fetchone()
                return matching_command is not None


@bot.listen()
async def register_commands_on_startup(event: hikari.StartingEvent) -> None:
    await register_commands()


async def register_commands() -> None:
    """Register ping and info commands."""
    application = await bot.rest.fetch_application()
    commands = await add_command.slash_builder() + await user_command.slash_builder()

    await bot.rest.set_application_commands(
        application=application.id,
        commands=commands,
        guild=COMMAND_GUILD_ID,
    )


@bot.listen()
async def handle_interactions(event: hikari.InteractionCreateEvent) -> None:
    """Listen for slash commands being executed."""
    if not isinstance(event.interaction, hikari.CommandInteraction):
        # only listen to command interactions, no others!
        return

    await event.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE, f"Working..."
    )

    if await add_command.is_matching_command(event):
        await add_command.handler(event)
    elif await user_command.is_matching_command(event):
        await user_command.handler(event)


bot.run()
