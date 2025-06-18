
import inspect
from typing import Any, Awaitable, Callable, Self, Tuple, get_args, get_origin

from asyncpg import InsufficientPrivilegeError # type:ignore

from unrest.contexts.auth import AuthFunction, AuthResponse, NullTenant, Tenant, User, UnauthenticatedUser
from unrest.contexts import getLogger, query as _query, mutate as _mutate
from unrest.contexts import Unauthorized, usercontext
from unrest.contexts import getLogger, auth

from unrest import Payload, ContextError, ClientError, ServerError, Unauthorized
from unrest import http

from mangum import Mangum


# from unrest.tasks import TaskNotReady, TaskTimeout



log = getLogger(__name__)


class Service(http.Router):
    def __init__(self, name: str | None = None, parent: Self | None = None):
        super().__init__()
        self.name = name
        self._authfunction: AuthFunction = None # type:ignore
        if parent is not None:
            parent.mount("/%s" % name, self, name=self.name)

    def add(self, route: http.Route):
        self.routes.append(route)
    
    async def authenticate(self, request: http.Request) -> AuthResponse:
        if self._authfunction is None:
            return UnauthenticatedUser(), NullTenant(request.url)
        return await self._authfunction(request)


class Endpoint:
    def __init__(self, func: Callable, service: Service):
        self.function = func
        self.returns = None
        self.payload = None
        self.service = service
        self.args: dict[str, Any] | None = {}
        self.kwargs: dict[str, Any] | None = {}
        
        if not inspect.iscoroutinefunction(func):
            raise RuntimeError("Request handlers must be async coroutines")

        def _is_payload(t):
            return issubclass(t, Payload) or issubclass(t, dict)

        def _get_type(annotation):
            if annotation is not None and annotation != inspect.Parameter.empty:
                if get_origin(annotation) is list:
                    args = get_args(annotation)
                    if len(args) == 1 and _is_payload(args[0]):
                        return (args[0], True)
                if _is_payload(annotation):
                    return (annotation, False)
            return None

        first = True
        sig = inspect.signature(func)
        for p in sig.parameters.values():
            if first:
                first = False
                self.payload = _get_type(p.annotation)
                if self.payload:
                    continue
            if p.default is not p.empty:
                self.kwargs[p.name] = p.default
            else:
                self.args[p.name] = None

        self.returns = _get_type(sig.return_annotation)

        if len(self.args) == 0:
            self.args = None
        if len(self.kwargs) == 0:
            self.kwargs = None        
    
    async def decode(self, req: http.Request) -> tuple[list, dict]:
        raise NotImplementedError("Request decoding not implemented")

    async def encode(self, req: http.Request, resp: Any | None) -> http.Response:
        raise NotImplementedError("Response encoding not implemented")

    async def __call__(self, request: http.Request) -> http.Response:
            try:
                user, tenant = await self.service.authenticate(request)
                with usercontext(user, tenant=tenant): 
                    (args, kwargs) = await self.decode(request)
                    response = await self.function(*args, **kwargs)
                    return await self.encode(request, response)
            except ClientError as ex:
                log.error(ex)
                return http.Response(status_code=400)
            except http.AuthenticationError:
                return http.Response(status_code=401)
            except Unauthorized as ex:
                log.warning(ex)
                return http.Response(status_code=401)
            except InsufficientPrivilegeError as ex:
                log.warning(ex)
                return http.Response(status_code=403)
            except ContextError as ex:
                log.error(ex)
                return http.Response(status_code=403)            
            except ServerError as ex:
                log.error(ex)
                return http.Response(status_code=500)
            # except TaskTimeout:
            #     raise HTTPException(status_code=504)
            # except TaskNotReady:
            #     raise HTTPException(status_code=202)
            except Exception as ex:
                log.exception(ex)
                return http.Response(status_code=500)



class Server(http.Starlette):
    def __init__(self) -> None:
        super().__init__()

    async def __call__(self, scope: http.Scope, receive: http.Receive, send: http.Send) -> None:        

        from unrest.api import get_instance as get_api
        from unrest.app import get_instance as get_app


        is_api_request = False
        for header in scope["headers"]:
            if header[0] == b'accept' and header[1] ==  b'application/json':#
                is_api_request = True

        if is_api_request:
            api = get_api()
            await api.__call__(scope, receive, send)
        else:
            app = get_app()
            await app.__call__(scope, receive, send)


class Serverless(Mangum):
    def __init__(self, *args, **kwargs):
        super().__init__(Server(*args, **kwargs), lifespan="auto")


