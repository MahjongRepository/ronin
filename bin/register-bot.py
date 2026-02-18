"""Register a bot account and print the API key.

Usage: uv run python bin/register-bot.py <bot_name>

The API key is printed once and never stored. Save it securely.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from shared.auth.file_repository import FileUserRepository
from shared.auth.service import AuthError, AuthService

# Default matches AuthSettings.users_file default
DEFAULT_USERS_FILE = "data/users.json"


async def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bot_name>")
        sys.exit(1)

    bot_name = sys.argv[1]
    users_file = os.environ.get("AUTH_USERS_FILE", DEFAULT_USERS_FILE)
    user_repo = FileUserRepository(users_file)
    auth_service = AuthService(user_repo)

    try:
        user, raw_api_key = await auth_service.register_bot(bot_name)
    except AuthError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Bot registered: {user.username} (id: {user.user_id})")
    print(f"API key: {raw_api_key}")
    print("Save this key securely - it cannot be retrieved again.")


if __name__ == "__main__":
    asyncio.run(main())
