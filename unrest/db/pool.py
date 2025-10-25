from contextvars import ContextVar
from contextlib import asynccontextmanager
from dataclasses import dataclass
from asyncpg import create_pool, Pool as BasePool
from asyncpg.connection import Connection

from unrest import context, config, getLogger

class PoolState:
    def __init__(self, conn: Connection, tenant: str, refcnt: int):
        self.conn = conn
        self.tenant = tenant
        self.refcnt = refcnt

# Holds pool connections that may have to be reconfigured for RLS
tenant_connections = ContextVar[PoolState]("tenant_connections")

log = getLogger(__name__)

class Pool:
    def __init__(self, **kwargs):
        from unrest.db import _setup_connection
        self.pool: BasePool = None # type:ignore
        self.args = {"init": _setup_connection, "min_size": 3, "command_timeout": 60, **kwargs}

    @asynccontextmanager
    async def acquire(self):

        if self.pool is None: 
            self.pool = await create_pool(**self.args) # type: ignore

        # NB: we need the USER context to set the correct tenant in Postgres for RLS
        tenant_id = str(context.tenant.identity)

        state = tenant_connections.get(None)
        old_tenant = None if state is None else state.tenant
        needs_conn = state is None or state.conn is None or state.conn._con is None
        needs_tenant = state is None or state.tenant != tenant_id
        
 
        if not needs_conn and not needs_tenant:
            yield state.conn
            return

        state = PoolState(
            conn=state.conn if not needs_conn else await self.pool.acquire(), 
            tenant=state.tenant if not needs_tenant else tenant_id,
            refcnt=state.refcnt + 1 if not needs_conn else 0,
        )
        token = tenant_connections.set(state) # type:ignore
        try:
            if needs_tenant:
                await state.conn.execute("SET rls.tenant = '%s';" % tenant_id)  
            yield state.conn
        finally:    
            try:
                if old_tenant is not None and old_tenant != tenant_id:
                    await state.conn.execute("SET rls.tenant = '%s';" % old_tenant)  
                if state.refcnt == 0:
                    await self.pool.release(state.conn)
            except Exception as e:
                log.warning("Error releasing connection back to pool: %s", e)
            tenant_connections.reset(token)
            

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
            