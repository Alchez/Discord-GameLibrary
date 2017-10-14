import json
import random

import discord
import requests
from cogs.utils import checks
from cogs.utils.chat_formatting import box, pagify
from cogs.utils.dataIO import dataIO
from discord.ext import commands


class Game:
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="game", pass_context=True)
    async def game(self, ctx):
        "Get a random game common to all online users"

        # Checks if a subcommand has been passed or not
        if ctx.invoked_subcommand is None:
            suggestions = get_suggestions(get_all_users(ctx))

            if suggestions:
                await self.bot.say("Let's play some {}!".format(random.choice(suggestions)))
            else:
                await self.bot.say("You do not have any games, go buy some!")

    @game.command(pass_context=True)
    async def add(self, ctx, game):
        "Add a game to your game list"

        user = ctx.message.author

        if add(game, user.id):
            await self.bot.say("{}, {} was added to your library.".format(user.mention, game))
        else:
            await self.bot.say("{}, you already have this game in your library.".format(user.mention))

    @game.command(pass_context=True)
    @checks.admin_or_permissions(manage_messages=True)
    async def addto(self, ctx, game, user):
        "Add a game to any user's game list"

        if add(game, user.id):
            await self.bot.say("{} was added to {}'s' library.".format(game, user.nick))
        else:
            await self.bot.say("{} already has this game in their library.".format(user.nick))

    @game.command(pass_context=True)
    async def remove(self, ctx, game):
        "Remove a game from your game list"

        user = ctx.message.author

        if remove(game, user.id):
            await self.bot.say("{}, {} was removed from your library.".format(user.mention, game))
        else:
            await self.bot.say("{}, you do not have this game in your library.".format(user.mention))

    @game.command(pass_context=True)
    @checks.admin_or_permissions(manage_messages=True)
    async def removefrom(self, ctx, game, user):
        "Remove a game from any user's game list"

        if remove(game, user.id):
            await self.bot.say("{} was removed from {}'s' library.".format(game, user.nick))
        else:
            await self.bot.say("{} does not have this game in their library.".format(user.nick))

    @game.command(pass_context=True)
    @checks.admin_or_permissions(manage_messages=True)
    async def removeuser(self, ctx, user: discord.Member=None):
        "Remove a user from the roster"

        game_list = get_games()

        if check_key(user.id):
            del game_list[user.id]
            dataIO.save_json("data/game/games.json", game_list)
            await self.bot.say("{}, you are way out of this league.".format(user.mention))
        else:
            await self.bot.say("That user does not exist in this league.")

    @game.command(pass_context=True)
    async def check(self, ctx, game, user: discord.Member=None):
        """Checks if a game exists in a user's (or all users') library

        game: Name of the game
        user: (Optional) If given, check the user's library, otherwise check all user libraries
        """

        game_list = get_games()

        if user:
            # Checks if a user has the game
            if game in game_list[user.id]:
                await self.bot.say("Aye {}, you have {} in your library.".format(user.mention, game))
            else:
                await self.bot.say("Nay {}, you do not have that game in your library.".format(user.mention))
            return

        users_with_games = []

        # Checks which user(s) has the game
        for userid, games in game_list.items():
            if game in games:
                player = ctx.message.server.get_member(userid)
                if player:
                    users_with_games.append(player.nick or player.name)

        if not users_with_games:
            await self.bot.say("None of you have {}!".format(game))
        else:
            await self.bot.say("The following of you have {}: {}".format(game, box("\n".join(users_with_games))))

    @game.command(pass_context=True)
    async def list(self, ctx, user: discord.Member=None):
        """
        Print out a user's game list

        user: (Optional) If given, list a user's game library, otherwise list the message user's library
        """

        if not user:
            user = ctx.message.author

        game_list = get_games()

        if check_key(user.id) and game_list.get(user.id, False):
            message = pagify(", ".join(sorted(game_list[user.id])), [', '])

            await self.bot.say("{}, your games:".format(user.mention))

            for page in message:
                await self.bot.say((box(page)))
        else:
            await self.bot.say("{}, you do not have any games. Add one using `[p]game add <game_name>` or link your Steam profile with `[p]game steamlink <steam_id>` and run `[p]game update`.".format(user.mention))

    @game.command(pass_context=True)
    async def suggest(self, ctx, choice=None):
        "Print out a list with all common games"

        suggestions = []

        if choice is None or choice.lower() == "all":
            suggestions = get_suggestions(get_all_users(ctx))
        elif choice.lower() == "voice":
            suggestions = get_suggestions(get_voice_users(ctx))
        elif choice.lower() == "online":
            suggestions = get_suggestions(get_online_users(ctx))
        else:
            await self.bot.say("Please enter a valid filter!")

        if not suggestions:
            await self.bot.say("You have **no games** in common, go buy some!")
            return

        await self.bot.say("You can play these games: \n")
        message = pagify("\n".join(suggestions), ['\n'])

        for page in message:
            await self.bot.say(box(page))

    @game.command(pass_context=True)
    async def poll(self, ctx):
        "Make a poll from common games"

        suggestions = get_suggestions(get_online_users(ctx))

        if not suggestions:
            await self.bot.say("You have **no games** in common, go buy some!")
            return

        id = create_strawpoll("What to play?", suggestions)
        await self.bot.say("Here's your strawpoll link: http://strawpoll.me/{}".format(id))

    @game.command(pass_context=True)
    async def steamlink(self, ctx, id, user: discord.Member=None):
        """
        Link a Steam profile with a Discord ID

        id: Steam Name or Steam ID (64-bit)
        user: (Optional) If given, link library to user, otherwise default to user of the message
        """

        if not user:
            user = ctx.message.author

        try:
            id = int(id)
            ids = get_steam_ids()
            ids[user.id] = id
        except:
            url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key=27B11158905342682CD23ED16830DC0D&vanityurl={id}&format=json".format(
                id=id)
            r = requests.get(url)
            response = json.loads(r.text).get('response')

            ids = get_steam_ids()
            if response.get('success') == 1:
                ids[user.id] = response.get('steamid')
            else:
                await self.bot.say("{}, there was a problem linking your Steam name. Please try again with your 64-bit Steam ID instead.".format(user.mention))

        dataIO.save_json("data/game/steamids.json", ids)

        if not check_key(user.id):
            game_list = get_games()
            game_list[user.id] = None
            dataIO.save_json("data/game/games.json", game_list)

        await self.bot.say("{}'s account has been linked with Steam.".format(user.mention))

    @game.command(pass_context=True)
    async def update(self, ctx, user: discord.Member=None):
        "Update a user's Steam game library"

        if not user:
            user = ctx.message.author

        id = get_user_steam_id(user.id)

        if not id:
            await self.bot.say("{}, your Discord ID is not yet linked with a Steam ID.".format(user.mention))
            return

        steam_games = get_steam_games(id)
        game_list = get_games(user.id)

        if game_list:
            game_list.extend(steam_games)
        else:
            game_list = steam_games

        set_user_games(user.id, list(set(game_list)))

        await self.bot.say("{}, your Steam games have been updated!".format(user.mention))


def setup(bot):
    bot.add_cog(Game(bot))


def get_games(userid=None):
    games = dataIO.load_json("data/game/games.json")
    if not userid:
        return games
    else:
        return games[userid]


def set_user_games(userid, game_list):
    games = get_games()
    games[userid] = game_list
    dataIO.save_json("data/game/games.json", games)


def get_steam_ids():
    return dataIO.load_json("data/game/steamids.json")


def get_user_steam_id(userid):
    ids = get_steam_ids()
    return ids.get(userid, None)


def get_steam_games(id):
    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key=27B11158905342682CD23ED16830DC0D&steamid={id}&include_appinfo=1&format=json".format(
        id=id)
    r = requests.get(url)
    games = [game.get('name') for game in json.loads(r.text).get(
        'response').get('games') if check_category(game.get('appid'))]
    return games


def check_key(userid):
    game_list = get_games()
    key_list = game_list.keys()

    if userid in key_list:
        return True
    else:
        return False


def create_key(userid):
    game_list = get_games()
    game_list[userid] = []
    dataIO.save_json("data/game/games.json", game_list)


def check_category(id):
    return True
    # url = "http://store.steampowered.com/api/appdetails?appids={id}".format(id=id)
    # r= requests.get(url)
    # data = json.loads(r.text)
    # if data.get('success'):
    #   categories = [game.get('id') for game in data.get(str(id)).get('data').get('categories')]
    #   mp_categories = [1, 9]
    #   return any(category in categories for category in mp_categories)
    # else:
    #   return False


def get_suggestions(users):
    if not users:
        return

    game_list = get_games()
    user_game_list = [game_list.get(user, []) for user in users]
    suggestions = set(user_game_list[0]).intersection(*user_game_list[1:])

    return sorted(list(suggestions))


def get_all_users(ctx):
    users = get_online_users(ctx)

    if not users:
        users = get_voice_users(ctx)

    return users


def get_online_users(ctx):
    users = []

    for user in ctx.message.server.members:
        if user.status.name == "online" and user.bot is False:
            users.append(user.id)

    return users


def get_voice_users(ctx):
    users = []

    for channel in ctx.message.server.channels:
        for user in channel.voice_members:
            if not user.bot:
                users.append(user.id)

    return users


def create_strawpoll(title, options):
    data = {
        "captcha": "false", "dupcheck": "normal", "multi": "true",
        "title": title,
        "options": options
    }
    resp = requests.post('http://strawpoll.me/api/v2/polls',
                         headers={'content-type': 'application/json'}, json=data)

    return json.loads(resp.text)['id']


def add(game, userid):
    game_list = get_games()

    if check_key(userid):
        if game in game_list[userid]:
            return False
        else:
            game_list[userid].append(game)
            dataIO.save_json("data/game/games.json", game_list)
            return True
    else:
        create_key(userid)
        game_list[userid].append(game)
        dataIO.save_json("data/game/games.json", game_list)
        return True


def remove(game, userid):
    game_list = get_games()

    if check_key(userid):
        if game not in game_list[userid]:
            return False
        else:
            game_list[userid].remove(game)
            dataIO.save_json("data/game/games.json", game_list)
            return True
    else:
        create_key(userid)
        return False
