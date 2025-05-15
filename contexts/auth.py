from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, Awaitable, Callable, Mapping, Protocol



class User:
    def __init__(self, id: str, display_name: str, props: Mapping[str, Any], claims: Mapping[str, bool]) -> None:
        self._id = id
        self._display_name = display_name
        self._claims = dict(claims)
        self._props = dict(props)

    @property
    def is_authenticated(self) -> bool:
        return False

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def identity(self) -> str:
        return self._id
    
    def __getitem__(self, key):
        return self._props[key]

    def get(self, key, default=None):
        return self._props.get(key, default)


class AuthenticatedUser(User):
    @property
    def is_authenticated(self) -> bool:
        return True
    
class UnauthenticatedUser(User):
    def __init__(self, id: str = "", display_name: str = "", props: Mapping[str, Any] = {}, claims: Mapping[str, bool] = {}) -> None:
        super().__init__(id, display_name, props, claims)

    @property
    def is_authenticated(self) -> bool:
        return False



AuthFunction = Callable[[str], Awaitable[User]]

schemes : dict[str, AuthFunction] = {}

def scheme(scheme="bearer") -> Callable:
    def decorator(f: AuthFunction) -> AuthFunction:
        key = scheme.lower()
        if key in schemes:
            raise ValueError(f"Authentication scheme {scheme} already registered")
        schemes[key] = f
        return f
    return decorator



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
        from contexts import context
        return user.is_authenticated and self._name in user._claims and user._claims[self._name] >= context._ctx._local    
    



def Unrestricted(user: User) -> bool:
    return True

def UserIsAuthenticated(user: User) -> bool:
    return user.is_authenticated


