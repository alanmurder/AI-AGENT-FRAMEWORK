"""Unit tests for Auth system (JWT + Password + API Key)."""

from harness.security.auth import TokenManager, APIKeyManager
from runtime.context_schema import UserContext, UserRole


def test_jwt_create_and_validate():
    tm = TokenManager(secret="test-secret")
    token = tm.create_token("user1", UserRole.ADMIN, "tenant1")
    ctx = tm.validate_token(token)
    assert ctx is not None
    assert ctx.user_id == "user1"
    assert ctx.role == UserRole.ADMIN
    assert ctx.tenant_id == "tenant1"


def test_jwt_invalid_token():
    tm = TokenManager(secret="test-secret")
    ctx = tm.validate_token("invalid-token")
    assert ctx is None


def test_jwt_wrong_secret():
    tm1 = TokenManager(secret="secret1")
    tm2 = TokenManager(secret="secret2")
    token = tm1.create_token("user1", UserRole.OPERATOR)
    ctx = tm2.validate_token(token)
    assert ctx is None


def test_password_hash_and_verify():
    tm = TokenManager(secret="test-secret")
    hashed = tm.hash_password("mypassword")
    assert tm.verify_password("mypassword", hashed)
    assert not tm.verify_password("wrongpassword", hashed)


def test_api_key_register_and_validate():
    akm = APIKeyManager()
    uc = UserContext(user_id="user2", role=UserRole.VIEWER, tenant_id="t1",
                    permissions=[], memory_path="", session_id="")
    akm.register_key("key-abc", uc)
    result = akm.validate_key("key-abc")
    assert result is not None
    assert result.user_id == "user2"


def test_api_key_invalid():
    akm = APIKeyManager()
    result = akm.validate_key("nonexistent")
    assert result is None


def test_api_key_revoke():
    akm = APIKeyManager()
    uc = UserContext(user_id="user3", role=UserRole.OPERATOR, tenant_id="t1",
                    permissions=[], memory_path="", session_id="")
    akm.register_key("key-xyz", uc)
    akm.revoke_key("key-xyz")
    result = akm.validate_key("key-xyz")
    assert result is None