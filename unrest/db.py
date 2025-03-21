from contextlib import asynccontextmanager
from functools import wraps
from inspect import iscoroutinefunction
from re import sub
from typing import AsyncGenerator

from asyncpg import InsufficientPrivilegeError, create_pool  # noqa
from asyncpg import Record as BaseRecord
from asyncpg.connection import Connection as BaseConnection

from unrest.context import context


class Connection(BaseConnection):
    pass


class Record(BaseRecord):
    pass


# def _caller() -> str:
#     frame = stack()[2][0]
#     return getmodule(frame).__name__ + "." + frame.f_code.co_qualname


class Fragment:
    def __init__(self, *args):
        self.template = args[0]
        self.params: dict = {}
        self.dependencies: dict[str, Fragment] = {}
        self.path = None
        self.label = None
        self.is_mutation = None
        for i, v in enumerate(args[1:]):
            if issubclass(type(v), Fragment):
                self.dependencies[str(i + 1)] = v
            else:
                self.params[str(i + 1)] = v

    def _visit(self, cte):
        for v in self.dependencies.values():
            v._visit(cte)
        cte.add(self)

    def __str__(self):
        return str(SqlExpression(self))


class SqlExpression:
    def __init__(self, frag: Fragment):
        self.blocks = {}
        self.expr = []
        self.args = []
        self.is_mutation = False
        frag._visit(self)
        if self.is_mutation and (frag.is_mutation is False or context.is_readonly):
            raise InsufficientPrivilegeError("Mutation in query context")

    def _hash(self, frag: Fragment):
        T = frag.template
        for k, v in frag.dependencies.items():
            T = sub(r"\$%s" % k, v.label, T)
        for k, v in frag.params.items():
            T = sub(r"\$%s" % k, str(v), T)
        return T

    def _rewrite(self, frag: Fragment):
        T = frag.template
        for k, v in frag.dependencies.items():
            T = sub(r"\$%s" % k, v.label, T)
        for k, v in frag.params.items():
            offset = len(self.args) + 1
            self.args.append(v)
            T = sub(r"\$%s" % k, "$%d" % offset, T)
        return T

    def add(self, frag: Fragment):
        path = frag.path or ""
        if path not in self.blocks:
            self.blocks[path] = {}

        hash = self._hash(frag)
        if hash not in self.blocks[path]:
            label = path + "." + str(len(self.blocks[path]) + 1)
            label = sub(".", "__", label)
            self.blocks[path][hash] = label

            sql = self._rewrite(frag)
            self.expr.append((label, sql))

            self.is_mutation = self.is_mutation or frag.is_mutation
        frag.label = self.blocks[path][hash]

    def __str__(self):
        buf = []
        for i, tup in enumerate(self.expr):
            if i + 1 == len(self.expr):
                buf.append("\n-- %s\n%s" % tup)
            elif i == 0:
                buf.append("with %s as (\n%s\n)" % tup)
            else:
                buf.append(",\n%s as (\n%s\n)" % tup)
        return "\n".join([x for x in ("".join(buf)).split("\n") if x.strip()])


class fetch(Fragment):
    async def __call__(self) -> list[dict]:
        cte = SqlExpression(self)
        return await context.db.fetch(str(cte), *cte.args)


class fetchrow(Fragment):
    async def __call__(self) -> dict:
        cte = SqlExpression(self)
        return await context.db.fetchrow(str(cte), *cte.args)


class iterate(Fragment):
    async def __call__(self) -> AsyncGenerator[dict, None]:
        cte = SqlExpression(self)
        async with context.db.acquire() as conn:
            async with conn.transaction():
                async for row in conn.cursor(str(cte), *cte.args):
                    yield row


class execute(Fragment):
    def __init__(self, *args):
        super().__init__(*args)
        self.is_mutation = True

    async def __call__(self) -> str:
        cte = SqlExpression(self)
        async with context.db.acquire() as conn:
            async with conn.transaction():
                return await conn.execute(str(cte), *cte.args)


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


@asynccontextmanager
async def lifespan(app):
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
    yield {}
