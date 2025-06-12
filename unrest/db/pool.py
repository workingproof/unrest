import json
from contextlib import asynccontextmanager
from asyncpg import create_pool, connect as _connect
from asyncpg.connection import Connection



class Pool:
    def __init__(self, **kwargs):
        from unrest.db import _setup_connection
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
