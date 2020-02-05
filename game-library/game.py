import asyncio
import json
import os
import random
from collections import defaultdict
from typing import List

import requests

import discord
from redbot.core import commands
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import box, pagify, warning
from redbot.core.utils.mod import check_permissions
from redbot.core.utils.predicates import MessagePredicate

MANAGE_MESSAGES = {"manage_messages": True}
STRAWPOLL_GET_ENDPOINT = "https://www.strawpoll.me/{poll_id}"
STRAWPOLL_CREATE_ENDPOINT = "https://www.strawpoll.me/api/v2/polls"
STEAM_RESOLVE_NAME_ENDPOINT = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={key}&vanityurl={steam_id}&format=json"
STEAM_GET_USER_GAMES_ENDPOINT = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={key}&steamid={steam_id}&include_appinfo=1&include_played_free_games=1&format=json"


class MemberNotInVoiceChannelError(Exception):
    def __init__(self):
        message = "You need to be in a voice channel for this to work"
        super().__init__(message)


class InvalidChannelFilterError(Exception):
    def __init__(self):
        message = "Please enter a valid filter -> either use `online` (default) for all online users or `voice` for all users in a voice channel"
        super().__init__(message)


class Game(commands.Cog):
    def __init__(self, bot):
        self.config = Config.get_conf(
            self, identifier=28784542245, force_registration=True)

        default_global = {
            "steamkey": ""
        }
        default_user = {
            "games": [],
            "steam_id": "",
            "steam_name": ""
        }

        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        self.bot = bot

    @commands.group(name="game")
    async def game(self, ctx: commands.Context) -> None:
        "Get a random game common to all online users (excluding 'dnd' users)"

        # Check if a subcommand has been passed or not
        if ctx.invoked_subcommand is None:
            if (suggestions := await self.get_suggestions(ctx)):
                await ctx.send(f"Let's play some {random.choice(suggestions)}!")

    @game.command()
    async def add(self, ctx: commands.Context, game: str, user: discord.Member = None) -> None:
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
            await ctx.send(f"{game} already exists in {user.mention}'s library.")
            return
        games.append(game)
        await self.config.user(user).games.set(games)
        await ctx.send(f"{game} was added to {user.mention}'s library.")

    @game.command()
    async def remove(self, ctx: commands.Context, game: str, user: discord.Member = None) -> None:
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
            await ctx.send(f"{game} is not in {user.mention}'s library.")

    @game.command()
    async def update(self, ctx: commands.Context, user: discord.Member = None) -> None:
        """
        Update a user's Steam game library

        user: If given, update the user's Steam games, otherwise default to user of the message
        """

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

        updated_games = await self.get_steam_games(user)
        if not updated_games:
            await ctx.send(f"Sorry, you need a Steam API key to make requests to Steam. Use `{ctx.prefix}game steamkey` for more information.")
            return

        current_games = await self.config.user(user).games()
        current_games.extend(updated_games)
        await self.config.user(user).games.set(list(set(current_games)))
        await ctx.send(f"{user.mention}'s Steam games have been updated!")

    @game.command()
    async def destroy(self, ctx: commands.Context, user: discord.Member = None) -> None:
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
    async def check(self, ctx: commands.Context, game: str, user: discord.Member = None) -> None:
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
            await ctx.send(f"{user.mention} does not have a game library yet. Use `{ctx.prefix}help game` to start adding games!")
            return

        if game in games:
            await ctx.send(f"Aye {user.mention}, you have {game} in your library.")
        else:
            await ctx.send(f"Nay {user.mention}, you do not have that game in your library.")

    async def _check_all(self, ctx: commands.Context, game: str, user: discord.Member) -> None:
        users_with_games = []

        # Check which users have the game
        all_users = await self.config.all_users()
        for discord_id, user_data in all_users.items():
            if game in user_data.get("games"):
                user = ctx.message.guild.get_member(discord_id)
                if user:
                    users_with_games.append(user.nick or user.name)

        if not users_with_games:
            await ctx.send(f"None of you have {game}!")
        else:
            users = box('\n'.join(users_with_games))
            await ctx.send(f"The following of you have {game}: {users}")

    @game.command()
    async def list(self, ctx: commands.Context, user: discord.Member = None) -> None:
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
            await ctx.send(f"{user.mention} does not have any games. Add one using either `{ctx.prefix}game add <game_name>` or sync with a Steam profile using `{ctx.prefix}game steamsync <steam_id>`.")
            return

        messages = pagify(", ".join(sorted(game_list)), [', '])
        await ctx.send(f"Please check your DM for the full list of games, {ctx.author.mention}.")
        await ctx.author.send(f"{user.mention}'s games:")

        for message in messages:
            await ctx.author.send((box(message)))

    @game.command()
    async def suggest(self, ctx: commands.Context, choice: str = None) -> None:
        """
        List out games common to all online users (or users in voice channels)

        choice: Defaults to 'online'. Either 'online' (for all online users; excluding users with 'dnd' status) or 'voice' (for all users in a voice channel))
        """

        await ctx.trigger_typing()

        if choice and choice.lower() not in ("online", "voice"):
            raise InvalidChannelFilterError()

        if choice is None or choice.lower() in ("online", "voice"):
            users = await self.get_users(ctx, choice)
            if len(users) <= 1:
                await ctx.send("You need more than one person online for this to work")
                return

            suggestions = await self.get_suggestions(ctx, users=users)

            if not suggestions:
                await ctx.send("You have exactly **zero** games in common, go buy a 4-pack!")
                return

            await ctx.send("You can play these games: \n")
            messages = pagify("\n".join(suggestions), ['\n'])
            for message in messages:
                await ctx.send(box(message))

    @game.command()
    async def poll(self, ctx: commands.Context, choice: str = None) -> None:
        """
        Poll from the common games of all online users (or users in voice channels)

        choice: Defaults to 'online'. Either 'online' (for all online users; excluding users with 'dnd' status) or 'voice' (for all users in a voice channel))
        """

        await ctx.trigger_typing()

        if choice and choice.lower() not in ("online", "voice"):
            raise InvalidChannelFilterError()

        if choice is None or choice.lower() in ("online", "voice"):
            suggestions = await self.get_suggestions(ctx, choice=choice)

            if not suggestions:
                await ctx.send("You have exactly **zero** games in common, go buy a 4-pack!")
                return

            poll_id = create_strawpoll("What to play?", suggestions)

            if poll_id:
                await ctx.send(f"Here's your strawpoll link: {STRAWPOLL_ENDPOINT.format(poll_id=poll_id)}")
            else:
                await ctx.send(f"""Phew! You have way too many games to create a poll. You should try `{ctx.prefix}game suggest` instead to get the full list of common games.""")

    @game.command()
    async def steamkey(self, ctx: commands.Context, key: str) -> None:
        """
        (One-time setup) Set the Steam API key to use `steamsync` and `update` commands

        key: An API key generated at https://steamcommunity.com/dev/apikey (login with your Steam profile and enter any domain to create one)
        """

        await ctx.trigger_typing()
        await self.config.steamkey.set(key)
        await ctx.send("The Steam API key has been successfully added! Delete the previous message for your own safety!")

    @game.command()
    async def steamsync(self, ctx: commands.Context, steam_id: str, user: discord.Member = None) -> None:
        """
        Sync a Steam profile's games with a Discord ID

        steam_id: Steam Name (found in your Custom URL -> steamcommunity.com/id/<name>) or Steam ID (64-bit ID -> steamcommunity.com/profiles/<id>)
        user: If given, sync library to user, otherwise default to user of the message
        """

        await ctx.trigger_typing()

        if not user:
            user = ctx.author

        try:
            # Either use the given 64-bit Steam ID to sync with Steam...
            int(steam_id)
        except ValueError:
            # ...or convert given name to a 64-bit Steam ID
            key = await self.config.steamkey()

            if not key:
                await ctx.send(f"Sorry, you need a Steam API key to make requests to Steam. Use `{ctx.prefix}game steamkey` for more information.")
                return

            url = STEAM_RESOLVE_NAME_ENDPOINT.format(key=key, steam_id=steam_id)
            resp = requests.get(url)
            response = json.loads(resp.text).get('response')

            if not response.get('success') == 1:
                await ctx.send(f"There was a problem syncing {user.mention}'s account with Steam name '{steam_id}'. Please try again with the 64-bit Steam ID instead.")
                return

            await self.config.user(user).steam_id.set(response.get("steamid"))

        steam_game_list = await self.get_steam_games(user)
        if steam_game_list:
            game_list = await self.config.user(user).games()
            game_list.extend(steam_game_list)
            await self.config.user(user).games.set(game_list)

        await ctx.send(f"{user.mention}'s account was synced with Steam.")

    async def get_steam_games(self, user: discord.Member) -> List[str]:
        key = await self.config.steamkey()

        if not key:
            return False

        steam_id = await self.config.user(user).steam_id()
        url = STEAM_GET_USER_GAMES_ENDPOINT.format(key=key, steam_id=steam_id)
        resp = requests.get(url)
        response = json.loads(resp.text).get('response')
        games = [game.get('name') for game in response.get('games')]
        return games

    async def get_suggestions(self, ctx: commands.Context, choice: str = None, users: List[str] = None) -> List[str]:
        if not users:
            users = await self.get_users(ctx, choice)

        all_user_data = await self.config.all_users()
        users_game_list = [all_user_data.get(user, {}).get("games") for user in users]

        if users_game_list:
            suggestions = set(users_game_list[0]).intersection(
                *users_game_list[1:])
            return sorted(list(suggestions))

    async def get_users(self, ctx: commands.Context, choice: str = None) -> List[str]:
        users = []

        if choice is None or choice.lower == "online":
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


def create_strawpoll(title, options):
    data = {
        "captcha": "false",
        "dupcheck": "normal",
        "multi": "true",
        "title": title,
        "options": options
    }

    resp = requests.post(STRAWPOLL_CREATE_ENDPOINT, headers={'content-type': 'application/json'}, json=data)
    if not resp.ok:
        return False

    return json.loads(resp.text).get('id')
