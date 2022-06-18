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

import os

import hikari
from . import cfg

bot = hikari.GatewayBot(token=cfg.main_token)


COMMAND_GUILD_ID = cfg.test_env if cfg.test_env else hikari.UNDEFINED

command_dict = {
    "xur": {"description": "Xur Infographic", "text": "https://kyber3000.com/Xur"}
}


@bot.listen()
async def register_commands_on_startup(event: hikari.StartingEvent) -> None:
    await register_commands()


async def register_commands() -> None:
    """Register ping and info commands."""
    application = await bot.rest.fetch_application()

    commands = [
        bot.rest.slash_command_builder(
            "add", "Add a link to the bot, only usable by Kyber et al"
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
        )
    ] + [
        bot.rest.slash_command_builder(name, command_dict[name]["description"])
        for name in command_dict
    ]

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

    if event.interaction.command_name == "add":
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE, f"Working..."
        )
        options = event.interaction.options

        # Sort the options into a dict
        options_dict = {}
        for option in options:
            options_dict[option.name] = option.value

        if options_dict["name"] in ["add", "edit", "remove"] + list(
            command_dict.keys()
        ):
            await event.interaction.edit_initial_response(
                "A command with that name already exists"
            )
            return

        command_dict[options_dict["name"]] = {
            "description": options_dict["description"],
            "text": options_dict["link"],
        }

        await register_commands()
        await event.interaction.edit_initial_response("Command added")
        return

    if event.interaction.command_name in command_dict:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            command_dict[event.interaction.command_name]["text"],
        )
        return


bot.run()
