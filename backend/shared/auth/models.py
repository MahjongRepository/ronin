from dataclasses import dataclass

from shared.dal.models import AccountType


@dataclass
class AuthSession:
    """
    Server-side session for authenticated users.
    """

    session_id: str  # UUID, stored in cookie
    user_id: str
    username: str
    created_at: float  # time.time()
    expires_at: float  # time.time() + TTL
    account_type: AccountType = AccountType.HUMAN
