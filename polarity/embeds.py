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
import typing as t

import hikari as h
import lightbulb as lb
import miru as m
import regex as re

from . import cfg
from .utils import follow_link_single_step

re_user_side_emoji = re.compile("(<a?)?:(\w+)(~\d)*:(\d+>)?")


def construct_emoji_substituter(
    emoji_dict: t.Dict[str, h.Emoji],
) -> t.Callable[[re.Match], str]:
    """Constructs a substituter for user-side emoji to be used in re.sub"""

    def func(match: re.Match) -> str:
        maybe_emoji_name = str(match.group(2))
        return str(
            emoji_dict.get(maybe_emoji_name)
            or emoji_dict.get(maybe_emoji_name.lower())
            or match.group(0)
        )

    return func


async def substitute_user_side_emoji(
    bot_or_emoji_dict: lb.BotApp | t.Dict[str, h.Emoji], text: str
) -> str:
    """Substitutes user-side emoji with their respective mentions"""

    if isinstance(bot_or_emoji_dict, h.GatewayBot):
        guild = bot_or_emoji_dict.cache.get_guild(
            cfg.kyber_discord_server_id
        ) or await bot_or_emoji_dict.rest.fetch_guild(cfg.kyber_discord_server_id)

        emoji_dict = {emoji.name: emoji for emoji in await guild.fetch_emojis()}
    else:
        emoji_dict = bot_or_emoji_dict

    # Substitutes user-side emoji with their respective mentions
    return re_user_side_emoji.sub(construct_emoji_substituter(emoji_dict), text)


class InteractiveBuilderView(m.View):
    @staticmethod
    async def ask_user_for_properties(
        ctx: m.ViewContext,
        property_names: t.Union[str, t.List[str]],
        old_values: t.Union[str, t.List[str]],
        required: t.Union[bool, t.List[bool]] = True,
        multi_line: bool = False,
    ) -> t.List[str]:
        """Asks the user for a property of the embed using a modal

        Returns the new value of the property if the user responds"""

        def is_list_like(obj):
            return isinstance(obj, tuple) or isinstance(obj, list)

        if not is_list_like(property_names):
            property_names = [property_names]
        if not is_list_like(old_values):
            old_values = [old_values]
        if not is_list_like(required):
            required = [required] * len(property_names)

        if not len(property_names) == len(old_values):
            raise ValueError("property_names and old_values must be the same length")

        modal = m.Modal(title=f"Edit {', '.join(property_names)}")
        custom_ids = [
            f"embed_{property_name.lower().replace(' ', '_')}"
            for property_name in property_names
        ]

        if multi_line:
            style = h.TextInputStyle.PARAGRAPH
        else:
            style = h.TextInputStyle.SHORT

        for custom_id, old_value, property_name, required_ in zip(
            custom_ids, old_values, property_names, required
        ):
            modal.add_item(
                m.TextInput(
                    label=property_name,
                    value=old_value,
                    style=style,
                    required=required_,
                    custom_id=custom_id,
                )
            )

        await ctx.respond_with_modal(modal)
        await modal.wait()

        if not modal.last_context:
            return

        await modal.last_context.defer()

        values = [
            modal.last_context.get_value_by_id(custom_id) for custom_id in custom_ids
        ]

        return values[0] if len(values) == 1 else values


class EmbedBuilderView(InteractiveBuilderView):
    """A view for building embeds as per user input"""

    def __init__(self, done_button_text="Done"):
        super().__init__(timeout=840)
        self.embed = None
        self.done.label = done_button_text

    # @m.button(style=h.ButtonStyle.PRIMARY, label="Add Field")
    # async def add_field(self, button: m.Button, ctx: m.ViewContext):
    #     """Adds a field to the embed"""
    #     pass

    # @m.button(style=h.ButtonStyle.DANGER, label="Remove Field")
    # async def remove_field(self, button: m.Button, ctx: m.ViewContext):
    #     """Removes a field from the embed"""
    #     pass

    @m.button(style=h.ButtonStyle.SECONDARY, label="Edit Title")
    async def edit_title(self, button: m.Button, ctx: m.ViewContext):
        """Edits the embed's title"""
        embed = ctx.message.embeds[0]
        embed.title = await self.ask_user_for_properties(
            ctx, "Title", embed.title, required=False
        )
        await ctx.edit_response(embed=embed)

    @m.button(style=h.ButtonStyle.SECONDARY, label="Edit Text")
    async def edit_description(self, button: m.Button, ctx: m.ViewContext):
        """Edits the embed's description"""
        embed: h.Embed = ctx.message.embeds[0]
        description = await self.ask_user_for_properties(
            ctx, "Body", embed.description, multi_line=True, required=False
        )
        bot: lb.BotApp = ctx.bot

        embed.description = await substitute_user_side_emoji(bot, description)
        await ctx.edit_response(embed=embed)

    @m.button(style=h.ButtonStyle.SECONDARY, label="Edit Color")
    async def edit_color(self, button: m.Button, ctx: m.ViewContext):
        """Edits the embed's color"""
        embed = ctx.message.embeds[0]
        color = await self.ask_user_for_properties(
            ctx, "Color", str(embed.color or cfg.embed_default_color), required=False
        )
        try:
            embed.color = h.Color.of(color)
        except ValueError as e:
            logging.error(f"Invalid color: {color}")
            logging.exception(e)
        else:
            await ctx.edit_response(embed=embed)

    @m.button(style=h.ButtonStyle.SECONDARY, label="Edit Author")
    async def edit_author(self, button: m.Button, ctx: m.ViewContext):
        """Edits the embed's author text"""
        embed: h.Embed = ctx.message.embeds[0]

        try:
            name = embed.author.name
        except AttributeError:
            name = ""

        try:
            icon = embed.author.icon.url
        except AttributeError:
            icon = ""

        try:
            url = embed.author.url
        except AttributeError:
            url = ""

        name, icon, url = await self.ask_user_for_properties(
            ctx,
            ["Author", "Icon URL", "Author URL"],
            [name, icon, url],
            required=False,
        )

        embed.set_author(name=name or None, icon=icon or None, url=url or None)
        await ctx.edit_response(embed=embed)

    @m.button(style=h.ButtonStyle.SECONDARY, label="Edit Image")
    async def edit_image(self, button: m.Button, ctx: m.ViewContext):
        """Edits the embed's image"""

        embed = ctx.message.embeds[0]
        image_url = await self.ask_user_for_properties(
            ctx, "Image URL", embed.image.url if embed.image else ""
        )

        image_url = await follow_link_single_step(image_url)
        embed.set_image(image_url)

        await ctx.edit_response(embed=embed)

    @m.button(style=h.ButtonStyle.SECONDARY, label="Edit Thumbnail")
    async def edit_thumbnail(self, button: m.Button, ctx: m.ViewContext):
        """Edits the embed's thumbnail"""

        embed = ctx.message.embeds[0]
        thumbnail_url = await self.ask_user_for_properties(
            ctx, "Thumbnail URL", embed.thumbnail.url if embed.thumbnail else ""
        )

        thumbnail_url = await follow_link_single_step(thumbnail_url)
        embed.set_thumbnail(thumbnail_url)

        await ctx.edit_response(embed=embed)

    @m.button(style=h.ButtonStyle.SECONDARY, label="Edit Footer")
    async def edit_footer(self, button: m.Button, ctx: m.ViewContext):
        """Edits the embed's footer text"""
        embed: h.Embed = ctx.message.embeds[0]

        try:
            text = embed.footer.text
        except AttributeError:
            text = ""

        try:
            icon = embed.footer.icon.url
        except AttributeError:
            icon = ""

        text, icon = await self.ask_user_for_properties(
            ctx,
            ["Footer", "Icon URL"],
            [text, icon],
            required=False,
        )

        embed.set_footer(text, icon=icon or None)
        await ctx.edit_response(embed=embed)

    @m.button(style=h.ButtonStyle.SUCCESS, label="Done")
    async def done(self, button: m.Button, ctx: m.ViewContext):
        """Finishes building the embed"""
        for item in self.children:
            item.disabled = True  # Disable all items attached to the view
        await ctx.edit_response(components=self)
        self.embed = ctx.message.embeds[0]
        self.stop()


async def build_embed_with_user(
    ctx: lb.Context, done_button_text="Done", existing_embed=None
) -> h.Embed:
    """Builds an embed as specified by the user

    Responds with a message with buttons allowing the user to specify
    embed properties. Returns the embed once the user is done."""
    embed = existing_embed or h.Embed(
        title="Embed Builder",
        description="Use the buttons below to build your embed!\n",
        color=cfg.embed_default_color,
    )

    view = EmbedBuilderView(done_button_text=done_button_text)
    response_proxy = await ctx.respond(
        embed=embed, components=view, flags=h.MessageFlag.EPHEMERAL
    )
    await view.start(response_proxy)
    await view.wait()
    return view.embed


# @lb.command("embed", description="Builds an embed as specified by the user")
# @lb.implements(lb.SlashCommand)
# async def embed_builder(ctx: lb.Context):
#     """Builds an embed as specified by the user"""
#     embed = await build_embed_with_user(ctx, done_button_text="Submit")
#     await ctx.get_channel().send(embed=embed)


def register(bot: lb.BotApp):
    # bot.command(embed_builder)
    pass
