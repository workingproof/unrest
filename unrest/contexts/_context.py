from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from functools import wraps
from contextvars import ContextVar
from inspect import iscoroutinefunction
from typing import Any, Callable, Optional
import uuid

from unrest.contexts.auth import Tenant, User, UnauthenticatedUser, UserPredicateFunction, Unrestricted
from unrest.http import Request

# defuser = UnauthenticatedUser("00000000-0000-0000-0000-000000000000", "", {}, {})

class ContextError(RuntimeError):
    pass

class Unauthorized(ContextError):
    pass

class Unauthenticated(ContextError):
    pass


@dataclass(kw_only=True)
class Context:
    id: str = str(uuid.uuid4())
    user: User = field(default_factory=lambda: UnauthenticatedUser())
    tenant: Tenant = field(default_factory=lambda: Tenant())
    
    _request: Optional[Request] = None
    _global: bool = None #type:ignore
    _local: bool = None #type:ignore
    _entrypoint: str = None #type:ignore
    _vars: dict[str, Any] = field(default_factory=dict)
    _stack: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        self._stack.append(self._vars)

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

    def copy(self) -> "Context":
        stack = [ dict(s) for s in self._stack ]
        return Context(
            id=self.id,
            user=self.user,
            tenant=self.tenant,
            _request=None,
            _global=self._global,
            _local=self._local,
            _entrypoint=self._entrypoint,
            _stack=stack,
            _vars=stack[-1],
        )



__ctx: ContextVar[Context] = ContextVar("context")

def get() -> Context:
    ctx =  __ctx.get(None)
    if ctx is None:
        ctx = Context()
        __ctx.set(ctx)
    return ctx

@asynccontextmanager
async def operationalcontext(is_mutation: bool, f: Callable, expr: UserPredicateFunction):
    try:
        ctx = get()
        _root   = ctx._global is None
        _local  = ctx._local
        _global = ctx._global
        _entry = ctx._entrypoint
        if _root:
            ctx._global = is_mutation
            ctx._entrypoint = f.__module__ + "." + f.__name__        
        ctx._local = is_mutation
        try:        
            if not expr(ctx.user):
               raise Unauthorized("User is not authorized: %s" % f.__name__)

            if ctx._global is False and is_mutation:
                raise ContextError("Cannot mutate in a query context: %s" % f.__name__)

            yield ctx
        except Exception as e:
            # TODO: e.g. log error
            raise
        finally:
            ctx._local = _local
            ctx._global = _global  
            ctx._entrypoint = _entry        
    except LookupError:
        raise ContextError("No context")

@contextmanager
def usercontext(user : User, tenant: Tenant | None = None):
    ctx = get()
    _user = ctx.user
    _tenant = ctx.tenant

    try:
        ctx.user = user
        if tenant is not None:
            ctx.tenant = tenant        
        yield
    finally:
        ctx.user = _user
        ctx.tenant = _tenant

@contextmanager
def systemcontext(tenant: Tenant | None = None):
    from unrest.contexts import auth
    ctx = get()
    if tenant is None:
        tenant  = ctx.tenant    
    _global = ctx._global
    _local = ctx._local
    with usercontext(auth.System(tenant=str(tenant.identity)), tenant=tenant):
        # System context is always mutation enabled
        try:
            ctx._global = True
            ctx._local = True
            yield
        finally:
            ctx._global = _global
            ctx._local = _local

@contextmanager
def restorecontext(context: Context):
    token = __ctx.set(context)
    try:
        yield
    finally:
        __ctx.reset(token)

@contextmanager
def requestcontext(request: Request | None = None):
    ctx = get()
    _req = ctx._request
    _id = ctx.id
    try:
        ctx.id = str(uuid.uuid4())
        ctx._request = request
        yield
    finally:
        ctx._request = _req
        ctx.id = _id


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
    def id(self):
        return self._ctx.id
    
    @property
    def user(self):
        return self._ctx.user

    @property
    def tenant(self):
        return self._ctx.tenant

    @property
    def request(self):
        # We should never need to use this but provided as a fallback
        return self._ctx._request

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



