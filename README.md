# Game Library Cog for [RedBot](https://github.com/Cog-Creators/Red-DiscordBot)
A Discord cog for creating user game lists, finding game list intersections, and some more stuff.

## Commands:
All the following commands need to be prefixed with '[p]game'. For example, if you want to manually add a game to your library with a '!' prefix, use:

    !game add (game_name)

### Steam:
* `steamkey` - Sets the Steam API key for the server (one-time setup; required to use the `steamlink` and `update` commands).
  * Visit the [Steam Web API Key](https://steamcommunity.com/dev/apikey) page, login with your Steam profile and fill out the short form to generate one - you can use any domain to do so.
* `steamlink` - Links a Steam library to a Discord ID
* `update` - Updates a user's game library with their linked Steam games (for new games and accidental deletions!).

### Non-Steam:
* `add` - Adds a game to a user's library - mostly useful for manually adding non-Steam games.

### Suggestions:
* `suggest` - Looks at the libraries of online users and displays all the common games (priority order: voice > online users)
* `poll` - Same as suggest, but instead creates a Strawpoll for users to vote on a game to play.

### Deletions:
* `remove` - Removes a game from a user's library (the `update` command will re-add all Steam games).
* `destroy` - Deletes the author user's library.

### Library:
* `list` - Prints out a user's entire game library (Steam + non-Steam).
* `check` - Checks for a game in a user's library, or for all valid users in the server.

---

Made with ♥ by [Alchez](https://github.com/Alchez) and [vjFaLk](https://github.com/vjFaLk)
