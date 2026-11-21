import argparse
import asyncio
import secrets
import sys
import time
import uuid

from lobby.auth.password import BcryptHasher
from lobby.auth.service import AuthError, AuthService
from lobby.auth.settings import AuthSettings
from lobby.dal.models import AccountType, Tournament
from lobby.db import Database, SqlitePlayerRepository, SqliteSessionRepository, SqliteTournamentRepository


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a tournament owned by a human account, registering the account if missing, and print "
        "the account's fresh API token (the previous one stops working) and the tournament id."
    )
    parser.add_argument("owner", help="the owner's username")
    parser.add_argument("name", help="the tournament's name")
    args = parser.parse_args()

    auth_settings = AuthSettings()
    db = Database(auth_settings.database_path)
    await db.open()

    try:
        player_repo = SqlitePlayerRepository(db)
        auth_service = AuthService(
            player_repo,
            SqliteSessionRepository(db),
            password_hasher=BcryptHasher(rounds=auth_settings.bcrypt_rounds),
        )
        owner = await player_repo.get_by_username(args.owner)
        if owner is None:
            owner = await auth_service.register(args.owner, secrets.token_urlsafe(24))
        elif owner.account_type != AccountType.HUMAN:
            print(f"Error: '{args.owner}' is not a human account")
            sys.exit(1)

        raw_api_key = await auth_service.issue_account_api_key(owner)
        tournament = Tournament(
            id=str(uuid.uuid4()), name=args.name, owner_user_id=owner.user_id, created_at=time.time()
        )
        await SqliteTournamentRepository(db).create_tournament(tournament)
    except AuthError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await db.close()

    print(f"Owner: {owner.username} (id: {owner.user_id})")
    print(f"API key: {raw_api_key}")
    print(f"Tournament id: {tournament.id}")


if __name__ == "__main__":
    asyncio.run(main())
