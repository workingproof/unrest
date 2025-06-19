from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import iscoroutinefunction
from typing import AsyncGenerator

from asyncpg import connect as _connect # type:ignore
from asyncpg.connection import Connection # type:ignore

from unrest.db import pool
from unrest.db.sql import Fragment, SqlExpression
from unrest.contexts import context, config

import json

async def connect(*args, **kwargs):
    conn = await _connect(*args, **kwargs)
    return await _setup_connection(conn)

async def _setup_connection(conn: Connection):
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    return conn

def _decorator(f, is_mutation):
    path = f.__module__ + "." + f.__name__
    if iscoroutinefunction(f):

        @wraps(f)
        async def wrapper(*args, **kwargs):
            action = await f(*args, **kwargs)
            action.path = path
            action.is_mutation = action.is_mutation or is_mutation
            return action

        return wrapper
    else:

        @wraps(f)
        def wrapper(*args, **kwargs):
            action = f(*args, **kwargs)
            action.path = path
            action.is_mutation = action.is_mutation or is_mutation
            return action

        return wrapper


def query(f):
    # TODO: perms and any DB specific magic
    return _decorator(f, False)


def mutate(f):
    # TODO: perms and any DB specific magic
    return _decorator(f, True)


@asynccontextmanager
async def acquire():
    async with pool.acquire() as conn:
        yield conn

@asynccontextmanager
async def transaction(*args, **kwargs):
    async with pool.transaction(*args, **kwargs) as conn:
        yield conn

async def _fetch(query: str, *args):
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def _fetchrow(query: str, *args):
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)

async def _iterate(query: str, *args):
    async with pool.transaction() as conn:
        async for row in conn.cursor(query, *args):
            yield row

async def _execute(query: str, *args):
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

class fetch(Fragment):
    async def __call__(self) -> list[dict]:
        cte = SqlExpression(self)
        return await _fetch(str(cte), *cte.args)


class fetchrow(Fragment):
    async def __call__(self) -> dict:
        cte = SqlExpression(self)
        return await _fetchrow(str(cte), *cte.args)


class iterate(Fragment):
    async def __call__(self) -> AsyncGenerator[dict, None]: 
        cte = SqlExpression(self)
        async for row in _iterate(str(cte), *cte.args):
            yield row

class execute(Fragment):
    def __init__(self, *args):
        super().__init__(*args)
        self.is_mutation = True

    async def __call__(self) -> str:
        cte = SqlExpression(self)
        return await _execute(str(cte), *cte.args)


