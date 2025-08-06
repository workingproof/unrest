from contextvars import ContextVar
from contextlib import asynccontextmanager
from asyncpg import create_pool, Pool as BasePool
from asyncpg.connection import Connection

from unrest import context, config, getLogger

_connection = ContextVar[Connection]("db_connection")

log = getLogger(__name__)

class Pool:
    def __init__(self, **kwargs):
        from unrest.db import _setup_connection
        self.pool: BasePool = None # type:ignore
        self.args = {"init": _setup_connection, "min_size": 3, "command_timeout": 60, **kwargs}

    @asynccontextmanager
    async def acquire(self):
        global _connection
        # NB: we need the USER context to set the correct tenant in Postgres for RLS
        conn = _connection.get(None)
        if conn is None or conn._con is None:
            if self.pool is None: 
                self.pool = await create_pool(**self.args) # type: ignore
            conn = await self.pool.acquire()            
            token = _connection.set(conn)
            try:
                await conn.execute("SET rls.tenant = '%s';" % str(context.tenant.identity))  
                yield conn
            finally:    
                try:
                    await self.pool.release(conn)
                except Exception as e:
                    log.warning("Error releasing connection back to pool: %s", e)
                _connection.reset(token)
        else:
            yield conn

    @asynccontextmanager
    async def transaction(self, *args, **kwargs):
        async with self.acquire() as conn:
            async with conn.transaction(*args, **kwargs):
                yield conn


# NB: Both pools and connections are context-aware
_readers: Pool = None #type:ignore
_writers: Pool = None #type:ignore

def get_instance():
    global _readers 
    global _writers

    # NB: we need the OPERATIONAL context to select the correct pool

    # if context._ctx._global is None:
    #     raise RuntimeError("Cannot access database pool outside of an operational context")

    if context._ctx._global is True or context._ctx._global is None:
        if _writers is None:
            master = config.get("POSTGRES_MUTATE_URI")
            if master is None:
                raise RuntimeError("Invalid Postgres DSN configuration")
            _writers = Pool(dsn=master, min_size=1, command_timeout=60)
        return _writers
    
    if context._ctx._global is False:
        if _readers is None:
            slave = config.get("POSTGRES_QUERY_URI")
            if slave is None:
                raise RuntimeError("Invalid Postgres DSN configuration")
            _readers = Pool(dsn=slave, min_size=3, command_timeout=60)
        return _readers
    
    raise RuntimeError("Invalid operational context for database access: %s" % context._ctx._global)

@asynccontextmanager
async def acquire():
    async with get_instance().acquire() as conn:
        yield conn

@asynccontextmanager
async def transaction(*args, **kwargs):
    async with get_instance().acquire() as conn:
        async with conn.transaction(*args, **kwargs):
            yield conn
            