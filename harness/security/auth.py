"""JWT + API Key authentication."""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
import bcrypt as _bcrypt

from runtime.context_schema import UserContext, UserRole


class TokenManager:
    """Manages JWT token creation and validation."""

    def __init__(self, secret: str, algorithm: str = "HS256", expire_minutes: int = 480):
        self.secret = secret
        self.algorithm = algorithm
        self.expire_minutes = expire_minutes

    def create_token(self, user_id: str, role: UserRole = UserRole.OPERATOR, tenant_id: str = "default") -> str:
        """Create a JWT token for a user."""
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.expire_minutes)
        payload = {
            "user_id": user_id,
            "role": role.value,
            "tenant_id": tenant_id,
            "exp": expire,
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def validate_token(self, token: str) -> Optional[UserContext]:
        """Validate a JWT token and return UserContext."""
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            user_id = payload.get("user_id")
            role = UserRole(payload.get("role", "operator"))
            tenant_id = payload.get("tenant_id", "default")
            if user_id is None:
                return None
            return UserContext(
                user_id=user_id,
                role=role,
                tenant_id=tenant_id,
            )
        except JWTError:
            return None

    def hash_password(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


class APIKeyManager:
    """Manages API Key authentication."""

    def __init__(self):
        self.api_keys: dict[str, UserContext] = {}

    def register_key(self, key: str, user_context: UserContext) -> None:
        """Register an API key for a user."""
        self.api_keys[key] = user_context

    def validate_key(self, key: str) -> Optional[UserContext]:
        """Validate an API key and return UserContext."""
        return self.api_keys.get(key)

    def revoke_key(self, key: str) -> None:
        """Revoke an API key."""
        self.api_keys.pop(key, None)


# ---------------------------------------------------------------------------
# Default users seeded on first start
# ---------------------------------------------------------------------------
DEFAULT_USERS: dict[str, dict[str, str]] = {
    "admin":    {"password": "admin123",  "role": "admin"},
    "manager":  {"password": "manager123", "role": "manager"},
    "operator": {"password": "operator123", "role": "operator"},
    "viewer":   {"password": "viewer123",  "role": "viewer"},
}


class UserStore:
    """Simple JSON-file user store with bcrypt password hashing."""

    def __init__(self, store_path: str = "data/users.json"):
        self._path = Path(store_path)
        if not self._path.is_absolute():
            self._path = Path.cwd() / self._path
        self._users: dict[str, dict[str, str]] = {}
        self._load_or_seed()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def authenticate(self, user_id: str, password: str) -> Optional[UserContext]:
        """Return UserContext if user exists and password matches, else None."""
        entry = self._users.get(user_id)
        if entry is None:
            return None
        if not _bcrypt.checkpw(password.encode("utf-8"), entry["password_hash"].encode("utf-8")):
            return None
        return UserContext(
            user_id=user_id,
            role=UserRole(entry["role"]),
            tenant_id="default",
        )

    def create_user(self, user_id: str, password: str, role: str = "operator") -> bool:
        """Create a new user. Returns False if user already exists."""
        if user_id in self._users:
            return False
        self._users[user_id] = {
            "password_hash": _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8"),
            "role": role,
        }
        self._save()
        return True

    def user_exists(self, user_id: str) -> bool:
        return user_id in self._users

    def get_user_context(self, user_id: str) -> Optional[UserContext]:
        entry = self._users.get(user_id)
        if entry is None:
            return None
        return UserContext(user_id=user_id, role=UserRole(entry["role"]), tenant_id="default")

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _load_or_seed(self) -> None:
        if self._path.exists():
            self._users = json.loads(self._path.read_text("utf-8"))
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            for uid, info in DEFAULT_USERS.items():
                self._users[uid] = {
                    "password_hash": _bcrypt.hashpw(
                        info["password"].encode("utf-8"), _bcrypt.gensalt()
                    ).decode("utf-8"),
                    "role": info["role"],
                }
            self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._users, indent=2, ensure_ascii=False), "utf-8")