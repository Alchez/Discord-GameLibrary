# Discord-GameLibrary
A discord cog for creating user game lists, finding game list intersections, and some more stuff.

## Commands:

### Steam:
* steamlink - Links a Steam library to a Discord ID. All users' libraries are stored in a JSON.
* update - Updates a user's game library.

### Non-Steam:
* add - Adds a game to the author user's library - mostly uesful for manually adding non-Steam games.
* addto - (Admin only) Adds a game to any specified user's library.
    
### Deletions:
* remove - Removes a game from the author user's library (the update command will re-add all Steam games).
* removefrom - (Admin only) Removes a game from any specified user's library.
* removeuser - (Admin only) Removes a user and their entire library from the JSON.
  
### Library:
* list - Prints out a user's entire game library (Steam + non-Steam)
* check - Checks for a game in a user's library, or for all users in the server.

### Suggestions:
* suggest - Looks at available users' libraries and displays all the common games (priority order: voice channel > online users)
* poll - Same as suggest, but instead creates a strawpoll for users to vote on.
