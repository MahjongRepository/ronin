"""
Register a bot account and print the API key.

Usage: python -m scripts.register_bot <bot_name>

The API key is printed once and never stored. Save it securely.
"""

import asyncio
import os
import sys

from shared.auth.password import SimpleHasher
from shared.auth.service import AuthError, AuthService
from shared.db import Database, SqlitePlayerRepository


async def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bot_name>")
        sys.exit(1)

    bot_name = sys.argv[1]
    db_path = os.environ.get("AUTH_DATABASE_PATH", "backend/storage.db")

    db = Database(db_path)
    db.connect()

    try:
        player_repo = SqlitePlayerRepository(db)
        # Bot registration only hashes API keys with SHA-256 (not passwords),
        # so the password hasher choice doesn't matter here.
        auth_service = AuthService(player_repo, password_hasher=SimpleHasher())
        player, raw_api_key = await auth_service.register_bot(bot_name)
    except AuthError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        db.close()

    print(f"Bot registered: {player.username} (id: {player.user_id})")
    print(f"API key: {raw_api_key}")
    print("Save this key securely - it cannot be retrieved again.")


if __name__ == "__main__":
    asyncio.run(main())
