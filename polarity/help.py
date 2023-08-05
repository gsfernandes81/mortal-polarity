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

import lightbulb as lb
import hikari as h
import typing as t


async def command_name_autocomplete(
    option: h.AutocompleteInteractionOption,
    interaction: h.AutocompleteInteraction,
) -> t.List[h.CommandOption] | None:
    bot: lb.BotApp = interaction.app
    value = option.value

    command_list: t.List[lb.Command] = [
        *bot._prefix_commands,
        *bot._slash_commands,
        *bot._message_commands,
        *bot._user_commands,
    ]

    autocompletions = []
    for command in command_list:
        if command.name.startswith(value):
            autocompletions.append(command.name)

    return autocompletions


class CustomHelpBot(lb.BotApp):
    def __init__(
        self,
        token: str,
        prefix: t.Optional[lb.app.PrefixT] = None,
        ignore_bots: bool = True,
        owner_ids: t.Sequence[int] = (),
        default_enabled_guilds: t.Union[int, t.Sequence[int]] = (),
        help_class: t.Optional[t.Type[lb.commands.help.HelpCommand]] = None,
        help_slash_command: bool = False,
        delete_unbound_commands: bool = True,
        case_insensitive_prefix_commands: bool = False,
        **kwargs: t.Any,
    ):
        super().__init__(
            token,
            prefix,
            ignore_bots,
            owner_ids,
            default_enabled_guilds,
            None,
            help_slash_command,
            delete_unbound_commands,
            case_insensitive_prefix_commands,
            **kwargs,
        )
        if help_class is not None:
            help_cmd_types: t.List[t.Type[lb.commands.base.Command]] = []

            if prefix is not None:
                help_cmd_types.append(lb.commands.prefix.PrefixCommand)

            if help_slash_command:
                help_cmd_types.append(lb.commands.slash.SlashCommand)

            if help_cmd_types:
                self._help_command = help_class(self)

                self._setup_help_command(help_cmd_types)

    def _setup_help_command(self, help_cmd_types: list) -> None:
        @lb.option(
            "obj",
            "Object to get help for",
            required=False,
            modifier=lb.commands.base.OptionModifier.CONSUME_REST,
            autocomplete=command_name_autocomplete,
        )
        @lb.command("help", "Get help information for the bot", auto_defer=True)
        @lb.implements(*help_cmd_types)
        async def __default_help(ctx: lb.Context) -> None:
            assert self._help_command is not None
            await self._help_command.send_help(ctx, ctx.options.obj)

        self.command(__default_help)
