import uuid
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from asyncpg import InsufficientPrivilegeError
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import Response

from unrest.auth import AuthenticationError, Unauthorized
from unrest.auth import get_instance as get_auth_backend
from unrest.context import context
from unrest.db import lifespan as db_lifespan
from unrest.observability import getLogger
from unrest.tasks import TaskNotReady, TaskTimeout
from unrest.tasks import lifespan as tasks_lifespan

log = getLogger(__name__)


class ClientError(Exception):
    pass


class ServerError(Exception):
    pass


@asynccontextmanager
async def lifespan(app):
    async with db_lifespan(app) as db_conf:
        async with tasks_lifespan(app) as tasks_conf:
            yield {**db_conf, **tasks_conf}


# FIXME: once we can sort/remove lifecycle under testing then we dont need this
_singleton = None


class UnrestRouter(Starlette):
    def __init__(self):
        global _singleton
        super().__init__(debug=False, lifespan=lifespan, middleware=[Middleware(AuthenticationMiddleware, backend=get_auth_backend())])
        _singleton = self

    def _addroute(self, path: str, f: Callable, readonly, method, handler) -> Callable:
        def _create_request_context(req: Request):
            return {"trace_id": str(uuid.uuid4()), "username": req.user.display_name or None, "is_authenticated": req.user.is_authenticated}

        async def wrapper(req: Request) -> Awaitable[Response]:
            ctx = _create_request_context(req)
            with context(**ctx):
                try:
                    context.set(readonly, req)
                    return await handler(req)
                except ClientError as ex:
                    log.error(ex)
                    raise HTTPException(status_code=400)
                except AuthenticationError:
                    raise HTTPException(status_code=401)
                except Unauthorized as ex:
                    log.warning(ex)
                    raise HTTPException(status_code=401)
                except InsufficientPrivilegeError as ex:
                    log.warning(ex)
                    raise HTTPException(status_code=403)
                except ServerError as ex:
                    log.error(ex)
                    raise HTTPException(status_code=500)
                except TaskTimeout:
                    raise HTTPException(status_code=504)
                except TaskNotReady:
                    raise HTTPException(status_code=202)
                except Exception as ex:
                    log.exception(ex)
                    raise HTTPException(status_code=500)

        fname = f.__module__ + "." + f.__name__
        self.router.add_route(path, wrapper, methods=[method], name=fname)
        return f
