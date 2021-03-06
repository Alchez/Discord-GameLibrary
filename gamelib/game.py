import asyncio
import json
import os
import random
from collections import defaultdict
from typing import List, Optional, Sequence, Union

import aiohttp
from steam import SteamID
from steam import WebAPI

import discord
from redbot.core import commands
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import box, pagify, warning
from redbot.core.utils.mod import check_permissions
from redbot.core.utils.predicates import MessagePredicate

MANAGE_MESSAGES = {"manage_messages": True}
STRAWPOLL_GET_ENDPOINT = "https://www.strawpoll.me/{poll_id}"
STRAWPOLL_CREATE_ENDPOINT = "https://www.strawpoll.me/api/v2/polls"
STEAM_GET_APPINFO_ENDPOINT = "https://store.steampowered.com/api/appdetails?appids={appid}"


class MemberNotInVoiceChannelError(Exception): pass
class InvalidChannelFilterError(Exception): pass


class Game(commands.Cog):
    """The class for creating and interacting with users' game libraries"""

    def __init__(self, bot):
        self.config = Config.get_conf(
            self, identifier=28784542245, force_registration=True)

        default_global = {
            "steamkey": ""
        }
        default_user = {
            "games": [],
            "steam_id": ""
        }

        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.group(name="game")
    async def game(self, ctx: commands.Context) -> None:
        "Get a random game common to either all users in your voice channel, or all current online users"

        # Check if a subcommand has been passed or not
        if ctx.invoked_subcommand is None:
            if (suggestions := await self.get_suggestions(ctx)):
                await ctx.send(f"Let's play some {random.choice(suggestions)}!")

    @game.command()
    async def add(self, ctx: commands.Context, game: str, user: Optional[discord.Member] = None) -> None:
        """
        Add a game to your library, or another user's library (admin permissions required)

        game: Name of the game to be added
        user: If given, add game to a user's game library, otherwise add to the message user's library
        """

        if user:
            await self._add_to(ctx, game, user)
        else:
            await self._add(ctx, game, ctx.author)

    @commands.admin_or_permissions(**MANAGE_MESSAGES)
    async def _add_to(self, ctx: commands.Context, game: str, user: discord.Member) -> None:
        await self._add(ctx, game, user)

    async def _add(self, ctx: commands.Context, game: str, user: discord.Member) -> None:
        games = await self.config.user(user).games()
        if game in games:
            await ctx.send(f"{game} already exists in {user.display_name}'s library.")
            return
        games.append(game)
        await self.config.user(user).games.set(games)
        await ctx.send(f"{game} was added to {user.mention}'s library.")

    @game.command()
    async def remove(self, ctx: commands.Context, game: str, user: Optional[discord.Member] = None) -> None:
        """
        Remove a game to your library, or another user's library (admin permissions required)

        game: Name of the game to be removed
        user: If given, destroy a user's game library, otherwise destroy the message user's library
        """

        if user:
            await self._remove_from(ctx, game, user)
        else:
            await self._remove(ctx, game, ctx.author)

    @commands.admin_or_permissions(**MANAGE_MESSAGES)
    async def _remove_from(self, ctx: commands.Context, game: str, user: discord.Member) -> None:
        await self._remove(ctx, game, user)

    async def _remove(self, ctx: commands.Context, game: str, user: discord.Member) -> None:
        games = await self.config.user(user).games()
        if game in games:
            games.remove(game)
            await self.config.user(user).games.set(games)
            await ctx.send(f"{game} was removed from {user.mention}'s library.")
        else:
            await ctx.send(f"{game} is not in {user.display_name}'s library.")

    @game.command()
    async def update(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """
        Update a user's Steam game library

        user: If given, update the user's Steam games, otherwise default to user of the message
        """

        await ctx.trigger_typing()

        if user:
            await self._update_for(ctx, user)
        else:
            await self._update(ctx, ctx.author)

    @commands.admin_or_permissions(**MANAGE_MESSAGES)
    async def _update_for(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._update(ctx, user)

    async def _update(self, ctx: commands.Context, user: discord.Member) -> None:
        steam_id = await self.config.user(user).steam_id()

        if not steam_id:
            await ctx.send(f"{user.mention}'s Discord profile is not yet connected to a Steam profile. Use `{ctx.prefix}game steamsync` to sync them.")
            return

        updated_games = await self.get_steam_games(ctx, user)
        if not updated_games:
            return

        current_games = await self.config.user(user).games()
        current_games.extend(updated_games)
        await self.config.user(user).games.set(list(set(current_games)))
        await ctx.send(f"{user.mention}'s Steam games have been updated!")

    @game.command()
    async def destroy(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """
        Delete your entire game library from this server

        user: If given, destroy a user's game library, otherwise destroy the message user's library
        """

        if user:
            await self._destroy_for(ctx, user)
        else:
            await self._destroy(ctx, ctx.author)

    @commands.admin_or_permissions(**MANAGE_MESSAGES)
    async def _destroy_for(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._destroy(ctx, user)

    async def _destroy(self, ctx: commands.Context, user: discord.Member) -> None:
        await ctx.send(warning("Are you sure? (yes/no)"))

        try:
            predicate = MessagePredicate.yes_or_no(ctx)
            await self.bot.wait_for('message', timeout=15, check=predicate)
        except asyncio.exceptions.TimeoutError:
            await ctx.send("Yeah, that's what I thought.")
        else:
            if predicate.result is True:
                games = await self.config.user(user).games()
                games.clear()
                await self.config.user(user).games.set(games)
                await ctx.send(f"{user.mention}, your game library has been nuked")
            else:
                await ctx.send("Well, that was close!")

    @game.command()
    async def check(self, ctx: commands.Context, game: str, user: Optional[discord.Member] = None) -> None:
        """
        Check if a game exists in a user's library (or all users' libraries)

        game: Name of the game
        user: If given, check the user's library, otherwise check all user libraries
        """

        if user:
            await self._check(ctx, game, user)
        else:
            await self._check_all(ctx, game, ctx.author)

    async def _check(self, ctx: commands.Context, game: str, user: discord.Member) -> None:
        games = await self.config.user(user).games()
        if not games:
            await ctx.send(f"{user.display_name} does not have a game library yet. Use `{ctx.prefix}help game` to start adding games!")
            return

        if game in games:
            await ctx.send(f"Aye, {user.display_name} has {game}.")
        else:
            await ctx.send(f"Nay, {user.display_name} does not have {game}.")

    async def _check_all(self, ctx: commands.Context, game: str, user: discord.Member) -> None:
        users_with_games = []

        # Check which users have the game
        all_users = await self.config.all_users()
        for discord_id, user_data in all_users.items():
            if game in user_data.get("games"):
                user = ctx.message.guild.get_member(discord_id)
                if user:
                    users_with_games.append(user.display_name)

        if not users_with_games:
            await ctx.send(f"None of you have {game}!")
        else:
            users = box('\n'.join(users_with_games))
            await ctx.send(f"The following of you have {game}: {users}")

    @game.command()
    async def list(self, ctx: commands.Context, user: Optional[discord.Member] = None) -> None:
        """
        Print out a user's game list (sends as a DM)

        user: If given, list a user's game library, otherwise list the message user's library
        """

        if user:
            await self._list_for(ctx, user)
        else:
            await self._list(ctx, ctx.author)

    async def _list_for(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._list(ctx, user)

    async def _list(self, ctx: commands.Context, user: discord.Member) -> None:
        game_list = await self.config.user(user).games()
        if not game_list:
            await ctx.send(f"{user.display_name} does not have any games. Start adding them using `{ctx.prefix}game add` or sync with a Steam profile using `{ctx.prefix}game steamsync`.")
            return

        messages = pagify(", ".join(sorted(game_list)), [', '])
        await ctx.send(f"Please check your DM for the full list of games, {ctx.author.mention}.")
        await ctx.author.send(f"{user.display_name}'s games:")

        for message in messages:
            await ctx.author.send((box(message)))

    @game.command()
    async def suggest(self, ctx: commands.Context, choice: Optional[str] = None) -> None:
        """
        List out games common to either all users in your voice channel, or all current online users

        choice: Defaults to 'voice'. Can be either:
            - 'online' (for all online users; honours 'dnd' status) or,
            - 'voice' (for all users in a voice channel; doesn't honour 'dnd' status)
        """

        await ctx.trigger_typing()

        if choice and choice.lower() not in ("online", "voice"):
            await ctx.send("Please enter a valid filter -> either use `online` (default) for all online users or `voice` for all users in a voice channel")
            return

        suggestions = await self.get_suggestions(ctx, choice)

        if not suggestions:
            if suggestions is not None:
                await ctx.send("You have exactly **zero** games in common, go buy a 4-pack!")
            return

        await ctx.send("You can play these games: \n")
        messages = pagify("\n".join(suggestions), ['\n'])
        for message in messages:
            await ctx.send(box(message))

    @game.command()
    async def poll(self, ctx: commands.Context, choice: Optional[str] = None) -> None:
        """
        Poll from the common games of either all users in your voice channel, or all current online users

        choice: Defaults to 'voice'. Can be either:
            - 'online' (for all online users; honours 'dnd' status) or,
            - 'voice' (for all users in a voice channel; doesn't honour 'dnd' status)
        """

        await ctx.trigger_typing()

        if choice and choice.lower() not in ("online", "voice"):
            await ctx.send("Please enter a valid filter -> either use `online` (default) for all online users or `voice` for all users in a voice channel")
            return

        suggestions = await self.get_suggestions(ctx, choice)

        if not suggestions:
            if suggestions is not None:
                await ctx.send("You have exactly **zero** games in common, go buy a 4-pack!")
            return

        poll_id = await self.create_strawpoll(ctx, "What to play?", suggestions)
        if poll_id:
            await ctx.send(f"Here's your strawpoll link: {STRAWPOLL_GET_ENDPOINT.format(poll_id=poll_id)}")

    @game.command()
    async def steamkey(self, ctx: commands.Context, key: str) -> None:
        """
        (One-time setup) Set the Steam API key to use `steamsync` and `update` commands

        key: An API key generated at https://steamcommunity.com/dev/apikey (login with your Steam profile and enter any domain to create one)
        """

        await ctx.trigger_typing()
        await self.config.steamkey.set(key)
        await ctx.send("The Steam API key has been successfully added. Delete the previous message for your own safety!")

    @game.command()
    async def steamsync(self, ctx: commands.Context, steam_id: str, user: Optional[discord.Member] = None) -> None:
        """
        Sync a Steam profile's games with a Discord ID

        steam_id: Steam Name (found in your Custom URL -> steamcommunity.com/id/<name>) or Steam ID (64-bit ID -> steamcommunity.com/profiles/<id>)
        user: If given, sync library to user, otherwise default to user of the message

        Examples:
        ```
            [p]game steamsync Alyx
            [p]game steamsync Alyx @Alyx
            [p]game steamsync 76561198221914843
            [p]game steamsync 76561198221914843 @Alyx
        ```
        """

        await ctx.trigger_typing()

        if not user:
            user = ctx.author

        steam_user = SteamID(steam_id)
        if steam_user.is_valid():
            # Either use the given 64-bit Steam ID to sync with Steam...
            steam_id_64 = steam_user.as_64
        else:
            # ...or convert given name to a 64-bit Steam ID
            steam_client = await self.get_steam_client(ctx)

            if steam_client is None:
                return

            steam_name = steam_client.ISteamUser.ResolveVanityURL(vanityurl=steam_id)

            if steam_name.get("response", {}).get("success") != 1:
                await ctx.send(f"There was a problem syncing {user.mention}'s account with Steam ID '{steam_id}'. Please try again with the 64-bit Steam ID instead.")
                return

            steam_id_64 = steam_name.get("response", {}).get("steamid")

        await self.config.user(user).steam_id.set(steam_id_64)

        steam_game_list = await self.get_steam_games(ctx, user)
        if steam_game_list:
            game_list = await self.config.user(user).games()
            game_list.extend(steam_game_list)
            game_list = list(set(game_list))
            await self.config.user(user).games.set(game_list)

        await ctx.send(f"{user.mention}'s account was synced with Steam.")

    async def get_steam_client(self, ctx: commands.Context) -> Union[WebAPI, None]:
        key = await self.config.steamkey()

        if not key:
            await ctx.send(f"Sorry, you need a Steam API key to make requests to Steam. Use `{ctx.prefix}game steamkey` for more information.")
            return

        try:
            steam_client = WebAPI(key=key)
        except OSError:
            await ctx.send(f"There was an error connecting to Steam. Either the provided Steam key is invalid, or try again later.")
            return

        return steam_client

    async def get_steam_games(self, ctx: commands.Context, user: discord.Member) -> List[str]:
        steam_games = []
        steam_id = await self.config.user(user).steam_id()
        steam_client = await self.get_steam_client(ctx)

        if steam_client is None:
            return steam_games

        user_steam_games = steam_client.IPlayerService.GetOwnedGames(steamid=steam_id, include_played_free_games=True, include_appinfo=True, appids_filter=None)
        games = user_steam_games.get("response", {}).get("games")

        if not games:
            return steam_games

        steam_games = [game.get('name') for game in games]
        return steam_games

    async def get_suggestions(self, ctx: commands.Context, choice: Optional[str] = None) -> Union[List[str], None]:
        # Fetch applicable users based on user choice
        try:
            users = await self.get_users(ctx, choice)
        except MemberNotInVoiceChannelError:
            await ctx.send("You need to be in a voice channel")
            return
        else:
            if len(users) <= 1:
                await ctx.send("You need more than one person online")
                return

        # Build the list of game suggestions
        suggestions = []
        user_data = await self.config.all_users()

        for user in users:
            games = user_data.get(user, {}).get("games", [])
            if games:
                suggestions.append(games)

        if suggestions:
            suggestions = set(suggestions[0]).intersection(*suggestions[1:])
            return sorted(list(suggestions))

    async def get_users(self, ctx: commands.Context, choice: Optional[str] = None) -> List[str]:
        users = []

        # If no choice is given, default to online users (priority: voice > online)
        if choice is None:
            try:
                users = await self.get_users(ctx, "voice")
            except MemberNotInVoiceChannelError:
                users = await self.get_users(ctx, "online")
        elif choice.lower() == "online":
            for user in ctx.message.guild.members:
                if user.status.name in ("idle", "online") and not user.bot:
                    users.append(user.id)
        elif choice.lower() == "voice":
            current_channel = ctx.author.voice
            if not current_channel:
                raise MemberNotInVoiceChannelError()

            for user in current_channel.channel.members:
                if not user.bot:
                    users.append(user.id)

        return users

    async def create_strawpoll(self, ctx: commands.Context, title: str, options: Sequence[str]) -> str:
        data = {
            "captcha": "false",
            "dupcheck": "normal",
            "multi": "true",
            "title": title,
            "options": options
        }

        async with self.session.post(STRAWPOLL_CREATE_ENDPOINT, json=data) as response:
            resp = await response.json()

        if resp.get("errorCode") == 40:
            await ctx.send(f"""Phew! You have way too many games to create a poll. You should try `{ctx.prefix}game suggest` instead to get the full list of common games.""")
            return ''
        elif resp.get("errorCode") == 99:
            await ctx.send("Something went wrong while trying to create the poll. Please report the issue to the cog owners.")
            return ''

        return resp.get('id')
