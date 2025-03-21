from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from starlette.requests import Request

from unrest import config
from unrest.auth import Claims, DefaultUser, User
from unrest.utils import LazyPool


class Frame:
    def __init__(self):
        self.peek: dict[str, Any] = {}
        self.stack = [self.peek]

    @contextmanager
    def push(self, **kwargs):
        self.peek = dict(self.peek)
        self.peek.update(kwargs)
        self.stack.append(self.peek)
        try:
            yield
        finally:
            self.stack.pop()
            self.peek = self.stack[-1]


_stack: ContextVar[Frame] = ContextVar("stack", default=Frame())

_readers: ContextVar[LazyPool] = ContextVar("readers", default=LazyPool(dsn=config.get("UNREST_QUERY_URI"), min_size=3, command_timeout=60))
_writers: ContextVar[LazyPool] = ContextVar("writers", default=LazyPool(dsn=config.get("UNREST_MUTATE_URI"), min_size=1, command_timeout=60))
_readonly: ContextVar[bool] = ContextVar("readonly", default=True)

_request: ContextVar[Request] = ContextVar("request")
_user: ContextVar[User] = ContextVar("user", default=DefaultUser())
_credentials: ContextVar[Claims] = ContextVar("credentials", default=Claims())


class Context:
    # def pools(self, readers: Pool, writers: Pool):
    #     _readers.set(readers)
    #     _writers.set(writers)

    def set(self, is_readonly: bool, req: Request = None):
        if req is not None:
            _request.set(req)
            _user.set(req.user)
            _credentials.set(req.auth)
        _readonly.set(is_readonly)
        # _readers.set(req.state.readers)
        # _writers.set(req.state.writers)

    @property
    def request(self):
        return _request.get()

    @property
    def user(self):
        return _user.get()

    @property
    def credentials(self):
        return _credentials.get()

    @property
    def db(self):
        if _readonly.get():
            return _readers.get()
        else:
            return _writers.get()

    @property
    def is_readonly(self):
        return _readonly.get()

    @property
    def _stack(self):
        return _stack.get()

    @contextmanager
    def unsafe(self):
        ro = _readonly.get()
        _readonly.set(False)
        try:
            with self._stack.push(unsafe=True):
                yield
        finally:
            _readonly.set(ro)

    @contextmanager
    def __call__(self, **kwargs):
        with self._stack.push(**kwargs):
            yield

    def __setitem__(self, key, item):
        self._stack.peek[key] = item

    def __getitem__(self, key):
        return self._stack.peek[key]

    def __repr__(self):
        return repr(self._stack.peek)

    def __len__(self):
        return len(self._stack.peek)

    def __delitem__(self, key):
        del self._stack.peek[key]

    def clear(self):
        return self._stack.peek.clear()

    def copy(self):
        return self._stack.peek.copy()

    def has_key(self, k):
        return k in self._stack.peek

    def update(self, *args, **kwargs):
        return self._stack.peek.update(*args, **kwargs)

    def keys(self):
        return self._stack.peek.keys()

    def values(self):
        return self._stack.peek.values()

    def items(self):
        return self._stack.peek.items()

    def pop(self, *args):
        return self._stack.peek.pop(*args)

    def __cmp__(self, dict_):
        return self.__cmp__(self._stack.peek, dict_)

    def __contains__(self, item):
        return item in self._stack.peek

    def __iter__(self):
        return iter(self._stack.peek)


context = Context()
