
from typing import Any, Awaitable, Callable

from unrest import getLogger, query as _query, mutate as _mutate, Unauthorized
from unrest import auth, http, routing
from unrest.contexts.auth import TokenAuthFunction

from .payload import JSONResponse, PayloadResponse
from .client import Client





log = getLogger(__name__)


class ApiEndpoint(routing.Endpoint):
    async def decode(self, req: http.Request) -> tuple[list, dict]:
        args : list[Any | None] = []
        kwargs = {}
        try:
            if self.payload: 
                js = await req.json()
                accepts_list = self.payload[1]
                have_list = type(js) is list

                if accepts_list and have_list:
                    args.append([self.payload[0](**x) for x in js])
                elif not(accepts_list or have_list):
                    args.append(self.payload[0](**js))
                elif accepts_list and not have_list:
                    args.append([self.payload[0](**js)])
                else:
                    raise RuntimeError("Invalid payload type")

            if self.args:
                for k in self.args:
                    args.append(req.path_params.get(k))
            if self.kwargs:
                for k, v in self.kwargs.items():
                    kwargs[k] = req.query_params.get(k, v)
        except Exception:
            raise routing.ClientError()    
        return args, kwargs

    async def encode(self, request: http.Request, resp: Any | None) -> http.Response:
        if resp is None:
            return JSONResponse(None, status_code=202)

        if isinstance(resp, http.Response):
            return resp

        if self.returns is None:
            return JSONResponse(resp)

        def _maybewrap(obj, payload_class):
            if isinstance(obj, payload_class):
                return obj
            else:
                return payload_class(**dict(obj))

        returns_list = self.returns[1]
        have_list = type(resp) is list
        if returns_list and have_list:
            return PayloadResponse([_maybewrap(x, self.returns[0]) for x in resp])
        elif not (returns_list or have_list):
            return PayloadResponse(_maybewrap(resp, self.returns[0]))
        else:
            raise RuntimeError("Invalid return type")





class Api(routing.Service):
    def authentication(self, scheme="bearer") -> Callable:
        def decorator(f: TokenAuthFunction) -> TokenAuthFunction:
            async def _authenticate(request: http.Request) -> routing.AuthResponse:
                if "Authorization" in request.headers:
                    try:
                        header = request.headers["Authorization"]
                        _scheme, credentials = header.split()
                        if scheme.lower() == _scheme.lower():
                            return await f(credentials, request.base_url) 
                    except Exception as ex:
                        raise Unauthorized("Invalid credentials: %s" % ex)
                return await f(None, request.base_url)
            self._authfunction = _authenticate
            return f
        return decorator
        
    def query(self, path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
        def decorator(f: Callable) -> Callable:
            name = f.__module__ + "." + f.__name__
            qry  = _query(perms)(f)
            point = ApiEndpoint(qry, self)
            async def wrapper(*args, **kwargs):
                return await point(*args, **kwargs)
            self.add(http.Route(path, wrapper, methods=["GET", "QUERY"], name=name))
            return qry
        return decorator

    def mutate(self, path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
        def decorator(f: Callable) -> Callable:
            name = f.__module__ + "." + f.__name__ 
            qry = _mutate(perms)(f)
            point = ApiEndpoint(qry, self)
            async def wrapper(*args, **kwargs):
                return await point(*args, **kwargs)
            self.add(http.Route(path, wrapper, methods=["POST"], name=name))
            return qry
        return decorator



def query(path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
    return get_instance().query(path, perms) 

def mutate(path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
    return get_instance().mutate(path, perms)

def authentication(scheme="bearer") -> Callable:
    return get_instance().authentication(scheme)

def abort(status_code) -> JSONResponse:
    return JSONResponse({}, status_code=status_code)

_services : dict[str, Api] = {}
def get_instance(name: str = "") -> Api:
    if name not in _services:
        _services[name] = Api(name)
    return _services[name]

# TODO: entity / resource bulk endpoints?

# def get(path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
#     def decorator(f: Callable) -> Callable:
#         q = _query(perms)(f)
#         router.add(ApiEndpoint("GET", path, q))
#         return q
#     return decorator

# def put(path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
#     def decorator(f: Callable) -> Callable:
#         m = _mutate(perms)(f)
#         router.add(ApiEndpoint("PUT", path, m))
#         return m
#     return decorator

# def delete(path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
#     def decorator(f: Callable) -> Callable:
#         m = _mutate(perms)(f)
#         router.add(ApiEndpoint("DELETE", path, m))
#         return m
#     return decorator
