import json
from contextlib import asynccontextmanager
from functools import wraps
from inspect import iscoroutinefunction
from typing import Callable, TypeVar

from asyncpg import create_pool
from asyncpg.connection import Connection

_singletons = {}

T = TypeVar("T")


def singleton(f: Callable[[], T]) -> Callable[[], T]:
    key = f.__module__ + "." + f.__name__
    if iscoroutinefunction(f):

        @wraps(f)
        async def get_instance():
            if key not in _singletons:
                _singletons[key] = await f()
            return _singletons[key]

        return get_instance
    else:

        @wraps(f)
        def get_instance():
            if key not in _singletons:
                _singletons[key] = f()
            return _singletons[key]

        return get_instance


async def _setup_connection(conn: Connection):
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    return conn


class LazyPool:
    def __init__(self, **kwargs):
        self.pool = None
        self.args = {"init": _setup_connection, "min_size": 3, "command_timeout": 60, **kwargs}

    async def get(self):
        if self.pool is None:
            self.pool = await create_pool(**self.args)
        return self.pool

    async def execute(self, *args, **kwargs):
        async with self.acquire() as conn:
            return await conn.execute(*args, **kwargs)

    async def fetch(self, *args, **kwargs):
        async with self.acquire() as conn:
            return await conn.fetch(*args, **kwargs)

    async def fetchrow(self, *args, **kwargs):
        async with self.acquire() as conn:
            return await conn.fetchrow(*args, **kwargs)

    @asynccontextmanager
    async def transaction(self, *args, **kwargs):
        async with self.acquire() as conn:
            async with conn.transaction(*args, **kwargs):
                yield conn

    @asynccontextmanager
    async def acquire(self):
        pool = await self.get()
        async with pool.acquire() as conn:
            yield conn
