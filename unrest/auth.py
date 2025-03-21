from functools import wraps
from hashlib import scrypt
from inspect import iscoroutinefunction
from typing import Awaitable, Callable, Mapping, Sequence

import bcrypt
from starlette.authentication import AuthCredentials, AuthenticationBackend, AuthenticationError, BaseUser, UnauthenticatedUser

from unrest.utils import singleton


class Unauthorized(Exception):
    pass


class Claims(AuthCredentials):
    pass


class User(BaseUser):
    def __init__(self, props: Mapping[str, any], claims: Sequence[str] = []) -> None:
        self._claims = set(claims)
        self._props = props

    def __getitem__(self, key):
        return self._props[key]

    def get(self, key, default=None):
        return self._props.get(key, default)

    def is_authorized(self, claim):
        return claim in self._claims

    def is_authorized_any(self, *args):
        return any(claim in self._claims for claim in args)

    def is_authorized_all(self, *args):
        return all(claim in self._claims for claim in args)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self._props.get("display_name") or self._props.get("username") or self._props.get("email")

    @property
    def identity(self) -> str:
        return self._props.get("id") or self._props.get("user_id") or self._props.get("email")

class DefaultUser(User):
    def __init__(self) -> None:
        User.__init__(self, {}, [])

    @property
    def is_authenticated(self) -> bool:
        return False

    @property
    def display_name(self) -> str:
        return ""

    @property
    def identity(self) -> str:
        return "00000000-0000-0000-0000-000000000000"

class AuthBackend(AuthenticationBackend):
    def __init__(self):
        self.schemes = {}

    def add(self, scheme: str, callback: Callable[[str], Awaitable[User]]):
        self.schemes[scheme.lower()] = callback

    async def authenticate(self, conn):

        if "Authorization" in conn.headers:
            try:
                header = conn.headers["Authorization"]
                scheme, credentials = header.split()
                handler = self.schemes.get(scheme.lower())
                user = await handler(credentials)
                if user:
                    return AuthCredentials(user._claims), user
            except Exception:
                raise AuthenticationError("Invalid credentials")
        elif len(conn.cookies) > 0:
            for key, val in conn.cookies.items():
                handler = self.schemes.get(key.lower())
                if handler:
                    try:
                        user = await handler(val)
                        if user:
                            return AuthCredentials(user._claims), user
                    except Exception:
                        raise


class UpstreamBackend(AuthenticationBackend):
    def __init__(self):
        self.schemes: dict[str, Callable[[str], Awaitable[User]]] = {}

    def add(self, scheme: str, callback: Callable[[str], Awaitable[User]]):
        self.schemes[scheme.lower()] = callback

    async def authenticate(self, conn):

        if "Authorization" not in conn.headers:
            raise AuthenticationError("Missing downstream credentials")
            
        try:
            header = conn.headers["Authorization"]
            scheme, credentials = header.split()
            handler = self.schemes.get(scheme.lower())
            await handler(credentials)            
        except Exception:
            raise AuthenticationError("Invalid downstream credentials")
            
        if len(conn.cookies) > 0:
            for key, val in conn.cookies.items():
                handler = self.schemes.get(key.lower())
                if handler:
                    try:
                        user = await handler(val)
                        if user:
                            return AuthCredentials(user._claims), user
                    except Exception:
                        raise

@singleton
def get_instance() -> AuthBackend:
    # return AuthBackend()
    return UpstreamBackend()


def scheme(scheme="bearer") -> Callable:
    def decorator(f: callable) -> callable:
        get_instance().add(scheme, f)
        return f

    return decorator

def scope(*args):
    from unrest.context import context

    scopes = list(args)

    def _check():
        if len(scopes) == 0:
            if context.user is None or isinstance(context.user, UnauthenticatedUser):
                raise Unauthorized("User is not authenticated")
        else:
            for scope in scopes:
                if scope in context.credentials.scopes:
                    return
            raise Unauthorized("User is not authorized")

    def decorator(f):
        if iscoroutinefunction(f):

            @wraps(f)
            async def checker(*args, **kwargs):
                _check()
                return await f(*args, **kwargs)

            return checker
        else:

            @wraps(f)
            def checker(*args, **kwargs):
                _check()
                return f(*args, **kwargs)

            return checker

    return decorator


def check_password(plaintext, salt, hash):
    if not plaintext:
        return False
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    if isinstance(salt, str):
        salt = salt.encode("utf-8")
    calculated_hash = scrypt(password=plaintext, salt=salt, n=1024, r=1, p=1, dklen=128)
    return calculated_hash.hex() == hash


def salt_and_hash_password(password):
    salt = bcrypt.gensalt()
    hashed = scrypt(password=password.encode("utf-8"), salt=salt, n=1024, r=1, p=1, dklen=128)
    return (salt.decode("utf-8"), hashed.hex())
