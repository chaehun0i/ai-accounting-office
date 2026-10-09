import hmac
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

from app.contracts.access_errors import AuthenticationRequired
from app.core.security import PasswordSecurity, TokenClaims, TokenSecurity, digest, random_token
from app.identity.auth.application.contracts import IdentityUnitOfWork
from app.identity.sessions.domain.entities import RefreshSession, RequestFacts
from app.identity.users.domain.entities import Principal, User, normalize_email


@dataclass(frozen=True)
class AuthResult:
    user: User = field(repr=False)
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_in: int


class AuthService:
    def __init__(
        self,
        factory: Callable[[], IdentityUnitOfWork],
        passwords: PasswordSecurity,
        tokens: TokenSecurity,
    ) -> None:
        self.factory = factory
        self.passwords = passwords
        self.tokens = tokens

    def _issue(
        self,
        uow: IdentityUnitOfWork,
        user: User,
        facts: RequestFacts,
        family_id: UUID | None = None,
    ) -> AuthResult:
        now = uow.now()
        sid, jti = uuid4(), random_token()
        claims = TokenClaims(user.id, sid, jti)
        refresh = self.tokens.issue("refresh", claims, now)
        session = RefreshSession(
            sid,
            user.id,
            family_id or uuid4(),
            digest(refresh),
            digest(jti),
            now,
            now + timedelta(seconds=self.tokens.refresh_seconds),
            user_agent_hash=facts.user_agent_hash,
            ip_prefix=facts.ip_prefix,
            last_seen_at=now,
        )
        uow.sessions.add(session)
        return AuthResult(
            user, self.tokens.issue("access", claims, now), refresh, self.tokens.access_seconds
        )

    def register(self, email: str, password: str, facts: RequestFacts) -> AuthResult:
        email = normalize_email(email)
        with self.factory() as uow:
            uow.security.limit("REGISTER_ATTEMPT", facts, uow.now(), digest(email))
            uow.security.record("REGISTER_ATTEMPT", facts, email_hash=digest(email))
            # 중복 계정 여부를 공개하지 않는 고정 인증 실패 응답을 사용합니다.
            if uow.users.by_email(email) is not None:
                result = None
            else:
                now = uow.now()
                user = User(
                    uuid4(),
                    email,
                    self.passwords.hash(password),
                    last_login_at=now,
                    created_at=now,
                    updated_at=now,
                )
                uow.users.add(user)
                result = self._issue(uow, user, facts)
                uow.security.record("LOGIN_SUCCEEDED", facts, user_id=user.id)
        if result is None:
            raise AuthenticationRequired()
        return result

    def login(self, email: str, password: str, facts: RequestFacts) -> AuthResult:
        email = normalize_email(email)
        with self.factory() as uow:
            uow.security.limit("login", facts, uow.now(), digest(email))
            user = uow.users.by_email(email, lock=True)
            valid = self.passwords.verify(password, user.password_hash if user else None)
            if user is None or not valid or user.status != "ACTIVE":
                uow.security.record("LOGIN_FAILED", facts, email_hash=digest(email))
                result = None
            else:
                user.last_login_at = user.updated_at = uow.now()
                if self.passwords.hasher.check_needs_rehash(user.password_hash):
                    user.password_hash = self.passwords.hash(password)
                uow.users.save(user)
                result = self._issue(uow, user, facts)
                uow.security.record("LOGIN_SUCCEEDED", facts, user_id=user.id)
        if result is None:
            raise AuthenticationRequired()
        return result

    def authenticate(self, access: str) -> Principal:
        claims = self.tokens.read(access, "access")
        with self.factory() as uow:
            user = uow.users.get(claims.user_id)
            session = uow.sessions.get(claims.user_id, claims.session_id)
            if (
                user is None
                or user.status != "ACTIVE"
                or session is None
                or session.revoked_at is not None
                or session.expires_at <= uow.now()
                or not hmac.compare_digest(session.jti_hash, digest(claims.jti))
            ):
                raise AuthenticationRequired()
            return Principal(user.id, session.id, user.email)

    def me(self, principal: Principal) -> User:
        with self.factory() as uow:
            user = uow.users.get(principal.user_id)
            if user is None or user.status != "ACTIVE":
                raise AuthenticationRequired()
            return user

    def refresh(self, refresh: str, facts: RequestFacts) -> AuthResult:
        # 잘못된 토큰도 rate limit에 포함하고 이 보안 기록은 별도 scope에서 확정합니다.
        with self.factory() as uow:
            uow.security.limit("REFRESH_ATTEMPT", facts, uow.now())
            uow.security.record("REFRESH_ATTEMPT", facts)
        claims = self.tokens.read(refresh, "refresh")
        result = None
        with self.factory() as uow:
            # 사용자 잠금을 먼저 잡아 rotation, logout-all, 신규 세션 발급을 직렬화합니다.
            user = uow.users.get(claims.user_id, lock=True)
            session = uow.sessions.get(claims.user_id, claims.session_id)
            now = uow.now()
            if user is None or user.status != "ACTIVE" or session is None:
                raise AuthenticationRequired()
            if not hmac.compare_digest(
                session.jti_hash, digest(claims.jti)
            ) or not hmac.compare_digest(session.refresh_token_hash, digest(refresh)):
                raise AuthenticationRequired()
            if session.rotated_at is not None:
                uow.sessions.revoke(
                    user.id, now, "TOKEN_REUSED", family_id=session.session_family_id
                )
                uow.security.record("REFRESH_REUSED", facts, user_id=user.id, session=session)
                uow.security.record(
                    "SESSION_FAMILY_REVOKED", facts, user_id=user.id, session=session
                )
            elif (
                session.revoked_at is not None
                or session.expires_at <= now
                or session.status != "ACTIVE"
            ):
                raise AuthenticationRequired()
            else:
                session.status = "ROTATED"
                session.rotated_at = session.last_seen_at = now
                uow.sessions.save(session)
                result = self._issue(uow, user, facts, session.session_family_id)
                uow.security.record("REFRESH_SUCCEEDED", facts, user_id=user.id, session=session)
        # 재사용 기록과 family revoke를 rollback하지 않도록 commit 뒤에 실패를 반환합니다.
        if result is None:
            raise AuthenticationRequired()
        return result

    def logout(
        self, principal: Principal, facts: RequestFacts, *, all_sessions: bool = False
    ) -> None:
        with self.factory() as uow:
            user = uow.users.get(principal.user_id, lock=True)
            session = uow.sessions.get(principal.user_id, principal.session_id)
            if user is None or session is None:
                raise AuthenticationRequired()
            if all_sessions:
                uow.sessions.revoke(user.id, uow.now(), "LOGOUT_ALL")
                uow.security.record("ALL_SESSIONS_REVOKED", facts, user_id=user.id)
            else:
                uow.sessions.revoke(
                    user.id, uow.now(), "LOGOUT", family_id=session.session_family_id
                )
                uow.security.record("SESSION_REVOKED", facts, user_id=user.id, session=session)
                uow.security.record(
                    "SESSION_FAMILY_REVOKED", facts, user_id=user.id, session=session
                )
