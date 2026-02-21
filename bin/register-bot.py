"""Register a bot account and print the API key.

Usage: uv run python bin/register-bot.py <bot_name>

The API key is printed once and never stored. Save it securely.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from shared.auth.service import AuthError, AuthService
from shared.auth.settings import AuthSettings
from shared.db import Database, SqlitePlayerRepository


async def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bot_name>")
        sys.exit(1)

    bot_name = sys.argv[1]
    # Only database_path and legacy_users_file are needed; supply a
    # placeholder for game_ticket_secret so the script works without
    # AUTH_GAME_TICKET_SECRET being set.
    auth_settings = AuthSettings(game_ticket_secret="unused")  # type: ignore[call-arg]

    db = Database(auth_settings.database_path)
    db.connect()
    db.migrate_from_json(auth_settings.legacy_users_file)

    try:
        player_repo = SqlitePlayerRepository(db)
        auth_service = AuthService(player_repo)

        try:
            player, raw_api_key = await auth_service.register_bot(bot_name)
        except AuthError as e:
            print(f"Error: {e}")
            sys.exit(1)

        print(f"Bot registered: {player.username} (id: {player.user_id})")
        print(f"API key: {raw_api_key}")
        print("Save this key securely - it cannot be retrieved again.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
