from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from contextvars import ContextVar
from inspect import iscoroutinefunction
from typing import Any, Callable
import uuid

from unrest.contexts.auth import NullTenant, Tenant, User, UnauthenticatedUser, UserPredicateFunction, Unrestricted


# defuser = UnauthenticatedUser("00000000-0000-0000-0000-000000000000", "", {}, {})

class ContextError(RuntimeError):
    pass

class Unauthorized(ContextError):
    pass

class Unauthenticated(ContextError):
    pass


class Context:
    def __init__(self, user: User | None = None, tenant: Tenant | None = None) -> None:
        self._id = str(uuid.uuid4())
        self._global: bool = None #type:ignore
        self._local: bool = None #type:ignore
        self._entrypoint: str = None #type:ignore
        self._user: User = UnauthenticatedUser() if user is None else user
        self._tenant: Tenant = NullTenant(None) if tenant is None else tenant # type:ignore
        self._vars: dict[str, Any] = {}
        self._stack = [self._vars]

    @contextmanager
    def set(self, **kwargs):
        self._vars = dict(self._vars)
        self._vars.update(kwargs)
        self._stack.append(self._vars)
        try:
            yield
        finally:
            self._stack.pop()
            self._vars = self._stack[-1]





__ctx: ContextVar[Context] = ContextVar("context", default=Context())

def get() -> Context:
    return __ctx.get()

@asynccontextmanager
async def operationalcontext(is_mutation: bool, f: Callable, expr: UserPredicateFunction):
    try:
        ctx = get()
        _root   = ctx._global is None
        _local  = ctx._local
        _global = ctx._global
        if _root:
            ctx._global = is_mutation
            ctx._entrypoint = f.__module__ + "." + f.__name__        
        ctx._local = is_mutation
        try:        
            if not expr(ctx._user):
               raise Unauthorized("User is not authorized: %s" % f.__name__)

            if ctx._global is False and is_mutation:
                raise ContextError("Cannot mutate in a query context: %s" % f.__name__)

            if _root:
                # Create a context for (root) DB connection and set tenant for RLS
                # FIXME: user and operational context now set so this is safe here...but ugly
                from unrest.db.pool import acquire
                async with acquire() as conn:
                    yield ctx
            else:
                yield ctx
        except Exception as e:
            # TODO: e.g. log error
            raise
        finally:
            ctx._local = _local
            ctx._global = _global          
    except LookupError:
        raise ContextError("No context")


@contextmanager
def usercontext(user : User, tenant: Tenant):
    token = __ctx.set(Context(user, tenant=tenant))
    try:
        yield
    finally:
        __ctx.reset(token)

def query(expr: UserPredicateFunction = Unrestricted):
    def decorator(f):
        if not iscoroutinefunction(f):
            raise RuntimeError("Query functions must be async coroutines")

        @wraps(f)
        async def wrapper(*args, **kwargs):
            async with operationalcontext(False, f, expr):
                return await f(*args, **kwargs)
        return wrapper
    return decorator

def mutate(expr: UserPredicateFunction = Unrestricted):
    def decorator(f):
        if not iscoroutinefunction(f):
            raise RuntimeError("Mutation functions must be async coroutines")
        @wraps(f)
        async def wrapper(*args, **kwargs):
            async with operationalcontext(True, f, expr):
                return await f(*args, **kwargs)
        return wrapper
    return decorator

class ContextWrapper:
    @property
    def _ctx(self):
        return get()

    @property
    def user(self):
        return self._ctx._user

    @property
    def tenant(self):
        return self._ctx._tenant

    # @contextmanager
    # def unsafe(self):
    #     ctx  = get()
    #     prev = ctx._global
    #     ctx._global = True
    #     try:
    #         with ctx.set(unsafe=True):
    #             yield
    #     finally:
    #         ctx._global = prev

    @contextmanager
    def __call__(self, **kwargs):
        with self._ctx.set(**kwargs):
            yield

    def __setitem__(self, key, item):
        self._ctx._vars[key] = item

    def __getitem__(self, key):
        return self._ctx._vars[key]

    def __repr__(self):
        return repr(self._ctx._vars)

    def __len__(self):
        return len(self._ctx._vars)

    def __delitem__(self, key):
        del self._ctx._vars[key]

    def clear(self):
        return self._ctx._vars.clear()

    def copy(self):
        return self._ctx._vars.copy()

    def has_key(self, k):
        return k in self._ctx._vars

    def update(self, *args, **kwargs):
        return self._ctx._vars.update(*args, **kwargs)

    def keys(self):
        return self._ctx._vars.keys()

    def values(self):
        return self._ctx._vars.values()

    def items(self):
        return self._ctx._vars.items()

    def pop(self, *args):
        return self._ctx._vars.pop(*args)

    def __cmp__(self, dict_):
        return self.__cmp__(self._ctx._vars, dict_)

    def __contains__(self, item):
        return item in self._ctx._vars

    def __iter__(self):
        return iter(self._ctx._vars)



