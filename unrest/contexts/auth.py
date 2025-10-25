from dataclasses import dataclass, field
from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, Awaitable, Callable, Mapping, Protocol, Tuple
import uuid

from unrest import http

null_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")
NULL_IDENTITY = str(null_uuid)

@dataclass(kw_only=True)
class Tenant:
    identity: str = NULL_IDENTITY
    display_name: str = ""
    props: Mapping[str, Any] = field(default_factory=dict)

    def __getitem__(self, key):
        return self.props[key]

    def get(self, key, default=None):
        return self.props.get(key, default)


@dataclass(kw_only=True)
class User:
    identity: str
    display_name: str
    tenant: str = NULL_IDENTITY
    props: Mapping[str, Any] = field(default_factory=dict)
    claims: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return False


    def __getitem__(self, key):
        return self.props[key]

    def get(self, key, default=None):
        return self.props.get(key, default)

    def is_authorized(self, claim: str) -> bool:
        from unrest import context
        if not self.is_authenticated:
            return False
        if context._ctx._local is not None:
            return claim in self.claims and self.claims[claim] >= context._ctx._local
        else:
            return claim in self.claims 


class AuthenticatedUser(User):
    @property
    def is_authenticated(self) -> bool:
        return True
    
class UnauthenticatedUser(User):
    def __init__(self, identity: str = str(null_uuid), display_name: str = "", props: Mapping[str, Any] = {}, claims: Mapping[str, bool] = {}, tenant: str = str(null_uuid)) -> None:
        super().__init__(identity=identity, display_name=display_name, props=props, claims=claims, tenant=tenant)

    @property
    def is_authenticated(self) -> bool:
        return False


class System(User):
    def __init__(self, tenant: str | None = None) -> None:
        super().__init__(identity=NULL_IDENTITY, display_name="__system__", tenant=tenant or NULL_IDENTITY)

    @property
    def is_authenticated(self) -> bool:
        return True


class UserPredicateFunction(Protocol):
    def __call__(self, user: User) -> bool:
        ...

class AndExpression(UserPredicateFunction):
    def __init__(self, left: UserPredicateFunction, right: UserPredicateFunction) -> None:
        self._left = left
        self._right = right

    def __call__(self, user: User) -> bool:
        return self._left(user) and self._right(user)
    
class OrExpression(UserPredicateFunction):
    def __init__(self, left: UserPredicateFunction, right: UserPredicateFunction) -> None:
        self._left = left
        self._right = right

    def __call__(self, user: User) -> bool:
        return self._left(user) or self._right(user)
    
class NotExpression(UserPredicateFunction):
    def __init__(self, expr: UserPredicateFunction) -> None:
        self._expr = expr

    def __call__(self, user: User) -> bool:
        return not self._expr(user)

class UserPredicate(UserPredicateFunction):
    def __and__(self, other: UserPredicateFunction) -> UserPredicateFunction:
        return AndExpression(self, other)
    def __or__(self, other: UserPredicateFunction) -> UserPredicateFunction:
        return OrExpression(self, other)
    def __invert__(self) -> UserPredicateFunction:
        return NotExpression(self)
    
class Claim(UserPredicate):
    def __init__(self, name: str) -> None:
        self._name = name
    def __call__(self, user: User) -> bool:
        from unrest.contexts import context
        return user.is_authenticated and self._name in user.claims and user.claims[self._name] >= context._ctx._local     
    



class UnrestrictedHelper(UserPredicate):
    def __call__(self, user: User) -> bool:
        return True
Unrestricted = UnrestrictedHelper()


class UserIsAuthenticatedHelper(UserPredicate):
    def __call__(self, user: User) -> bool:
        return user.is_authenticated
UserIsAuthenticated = UserIsAuthenticatedHelper()



AuthResponse = Tuple[User, Tenant | None]
AuthFunction = Callable[[http.Request], Awaitable[AuthResponse]]

TokenAuthFunction = Callable[[str|None, http.URL], Awaitable[AuthResponse]]
CookieAuthFunction = Callable[[str|None, http.URL], Awaitable[AuthResponse]]