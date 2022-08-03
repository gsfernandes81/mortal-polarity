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

import functools
import operator

import hikari
from lightbulb import context as context_
from lightbulb import errors
from lightbulb.checks import Check, _guild_only
from lightbulb.utils import permissions


async def _has_guild_permissions(
    context: context_.base.Context, *, perms: hikari.Permissions
) -> bool:
    _guild_only(context)

    channel = context.get_channel()
    if channel is None:
        context.bot.cache.get_guild_channel(
            context.channel_id
        ) or await context.bot.rest.fetch_channel(context.channel_id)

    assert context.member is not None and isinstance(channel, hikari.GuildChannel)
    missing_perms = ~permissions.permissions_in(channel, context.member) & perms
    if missing_perms is not hikari.Permissions.NONE:
        raise errors.MissingRequiredPermission(
            "You are missing one or more permissions required in order to run this command",
            perms=missing_perms,
        )
    return True


def has_guild_permissions(
    perm1: hikari.Permissions, *perms: hikari.Permissions
) -> Check:
    """
    Custom Async version of `lightbulb.checks.has_guild_permissions`
    Prevents the command from being used by a member missing any of the required
    permissions (this takes into account permissions granted by both roles and permission overwrites).

    Args:
        perm1 (:obj:`hikari.Permissions`): Permission to check for.
        *perms (:obj:`hikari.Permissions`): Additional permissions to check for.

    Note:
        This check will also prevent commands from being used in DMs, as you cannot have permissions
        in a DM channel.

    Warning:
        This check is unavailable if your application is stateless and/or missing the intent
        :obj:`hikari.Intents.GUILDS` and will **always** raise an error on command invocation if
        either of these conditions are not met.
    """
    reduced = functools.reduce(operator.or_, [perm1, *perms])
    return Check(functools.partial(_has_guild_permissions, perms=reduced))
