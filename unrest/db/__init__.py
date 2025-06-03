from functools import wraps
from inspect import iscoroutinefunction
from typing import AsyncGenerator

from asyncpg import Record as BaseRecord # type:ignore
from asyncpg.connection import Connection as BaseConnection # type:ignore

from .pool import Pool
from .sql import Fragment, SqlExpression
from unrest.contexts import context, config


class Connection(BaseConnection):
    pass


class Record(BaseRecord):
    pass


    # slave = config.get("UNREST_QUERY_URI")
    # master = config.get("UNREST_MUTATE_URI")
    # if slave and master:
    #     async with create_pool(dsn=slave, init=_setup_connection, min_size=3, command_timeout=60) as readers:
    #         async with create_pool(dsn=master, init=_setup_connection, min_size=1, command_timeout=60) as writers:
    #             yield {"readers": readers, "writers": writers}
    # elif master:
    #     async with create_pool(dsn=master, init=_setup_connection, min_size=3, command_timeout=60) as writers:
    #         yield {"readers": writers, "writers": writers}
    # elif slave:
    #     async with create_pool(dsn=slave, init=_setup_connection, min_size=3, command_timeout=60) as readers:
    #         yield {"readers": readers, "writers": None}
    # else:
    #     raise RuntimeError("Invalid Postgres DSN configuration")

_readers: Pool = None #type:ignore
_writers: Pool = None #type:ignore

def _pool():
    global _readers 
    global _writers
    if context._ctx._global is True:
        if _writers is None:
            master = config.get("POSTGRES_MUTATE_URI", config.get("POSTGRES_URI"))
            if master is None:
                raise RuntimeError("Invalid Postgres DSN configuration")
            _writers = Pool(dsn=master, min_size=1, command_timeout=60)
        return _writers
    else:
        if _readers is None:
            slave = config.get("POSTGRES_QUERY_URI")
            if slave is None:
                raise RuntimeError("Invalid Postgres DSN configuration")
            _readers = Pool(dsn=slave, min_size=3, command_timeout=60)
        return _readers


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
    return _decorator(f, False)


def mutate(f):
    return _decorator(f, True)


async def _fetch(query: str, *args):
    return await _pool().fetch(query, *args)

async def _fetchrow(query: str, *args):
    return await _pool().fetchrow(query, *args)

async def _iterate(query: str, *args):
    async with _pool().acquire() as conn:
        async with conn.transaction():
            async for row in conn.cursor(query, *args):
                yield row

async def _execute(query: str, *args):
    async with _pool().acquire() as conn:
        async with conn.transaction():
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


