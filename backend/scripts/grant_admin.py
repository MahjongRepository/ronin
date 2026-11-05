import argparse
import asyncio
import sys

from shared.auth.settings import AuthSettings
from shared.db import Database, SqlitePlayerRepository


async def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or revoke the admin flag of an account.")
    parser.add_argument("username")
    parser.add_argument("--revoke", action="store_true", help="revoke the flag instead of granting it")
    args = parser.parse_args()

    db = Database(AuthSettings().database_path)
    await db.open()

    try:
        player_repo = SqlitePlayerRepository(db)
        player = await player_repo.get_by_username(args.username)
        if player is None:
            print(f"Error: no account named '{args.username}'")
            sys.exit(1)

        await player_repo.set_admin(player.user_id, is_admin=not args.revoke)
    finally:
        await db.close()

    action = "revoked from" if args.revoke else "granted to"
    print(f"Admin {action} {player.username} (id: {player.user_id})")


if __name__ == "__main__":
    asyncio.run(main())
