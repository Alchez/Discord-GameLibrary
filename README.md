# Discord-GameLibrary
A discord cog for creating user game lists, finding game list intersections, and some more stuff.

## Commands:
All the following commands need to be prefixed with '[p]game'. For example, if you want to manually add a game to your library with a '!' prefix, use:

    !game add (game_name)

### Steam:
* steamlink - Links a Steam library to a Discord ID. All users' libraries are stored in a JSON.
* update - Updates a user's game library with new Steam games (or accidental deletions!).

### Non-Steam:
* add - Adds a game to the author user's library - mostly useful for manually adding non-Steam games.
* addto - (Admin only) Adds a game to any specified user's library.

### Suggestions:
* suggest - Looks at all the libraries for online users and displays all common games within Discord (priority order: voice channel > online users)
* poll - Same as suggest, but instead creates a Strawpoll for users to vote on a common game to play.

### Deletions:
* remove - Removes a game from the author user's library (the update command will re-add all Steam games).
* removefrom - (Admin only) Removes a game from any specified user's library.
* removeuser - (Admin only) Removes a user and their entire library from the JSON.

### Library:
* list - Prints out a user's entire game library (Steam + non-Steam).
* check - Checks for a game in a user's library, or for all valid users in the server.
