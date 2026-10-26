import asyncio
import sys

from shared.auth.password import BcryptHasher
from shared.auth.service import AuthError, AuthService
from shared.auth.session_store import AuthSessionStore
from shared.auth.settings import AuthSettings
from shared.db import Database, SqlitePlayerRepository


async def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bot_name>")
        sys.exit(1)

    bot_name = sys.argv[1]
    auth_settings = AuthSettings()

    db = Database(auth_settings.database_path)
    await db.open()

    try:
        player_repo = SqlitePlayerRepository(db)
        auth_service = AuthService(
            player_repo,
            AuthSessionStore(),
            password_hasher=BcryptHasher(rounds=auth_settings.bcrypt_rounds),
        )
        player, raw_api_key = await auth_service.register_bot(bot_name)
    except AuthError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await db.close()

    print(f"Bot registered: {player.username} (id: {player.user_id})")
    print(f"API key: {raw_api_key}")
    print("Save this key securely - it cannot be retrieved again.")


if __name__ == "__main__":
    asyncio.run(main())
