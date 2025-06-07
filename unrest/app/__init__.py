from typing import Any, Callable, Mapping

from unrest.http import Request, Response, HTMLResponse, RedirectResponse, Route, UploadFile
from unrest import context, getLogger, Unauthorized, query as _query, mutate as _mutate
from unrest import routing, auth

log = getLogger(__name__)


class ApplicationEndpoint(routing.Endpoint):
    async def authenticate(self, request: Request) -> auth.User | None:
        if len(request.cookies) > 0:
            for key, val in request.cookies.items():
                handler = get_instance()._schemes.get(key.lower())
                if handler:
                    try:
                        user = await handler(val)
                        if user:
                            return user
                    except Exception:
                        raise Unauthorized("Invalid credentials")
        return None

    async def decode(self, req: Request) -> tuple[list, dict]:
        args: list[Any|None] = []
        kwargs = {}
        form = {}

        # TODO: need to deal with file uploads: dict[str, UploadFile | str]
        # TODO: need to handle payload conversions
        try:
            if req.method == "POST":
                try:
                    form = dict(await req.form())
                except:  # noqa
                    pass

            # if self.function.payload:
            #     js = await req.json()
            #     if self.function.payload[1]:
            #         args.append([self.function.payload[0](**x) for x in js])
            #     else:
            #         args.append(self.function.payload[0](**js))

            if self.args:
                for k in self.args:
                    args.append(req.path_params.get(k))
            if self.kwargs:
                for k, v in self.kwargs.items():
                    fv = form.get(k, v)
                    if type(fv) is not UploadFile:
                        kwargs[k] = req.query_params.get(k, fv)

        except Exception:
            raise routing.ClientError()    
        return args, kwargs

    async def encode(self, request: Request, resp: Any | None) -> Response:
        if resp is None:
            return HTMLResponse(status_code=202)
        
        if isinstance(resp, Response):
            return resp

        # TODO: handle automatic templating???
        raise ValueError("Invalid response type")


class App(routing.Service):
    def get(self, path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
        def decorator(f: Callable) -> Callable:
            name = f.__module__ + "." + f.__name__
            q = _query(perms)(f)
            self.add(Route(path, ApplicationEndpoint(q), methods=["GET"], name=name)) 
            return q
        return decorator

    def post(self, path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
        def decorator(f: Callable) -> Callable:
            name = f.__module__ + "." + f.__name__
            m = _mutate(perms)(f)
            self.add(Route(path, ApplicationEndpoint(m), methods=["POST"], name=name)) 
            return m
        return decorator

    def redirect(self, url: str, status_code: int = 302, headers: Mapping[str, str] | None = None) -> RedirectResponse:
        return RedirectResponse(url, status_code=status_code, headers=headers)

    def abort(self, status_code) -> HTMLResponse:
        return HTMLResponse(status_code=status_code)


def get(path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
    return get_instance().get(path, perms) 

def post(path, perms: auth.UserPredicateFunction = auth.UserIsAuthenticated) -> Callable:
    return get_instance().post(path, perms)

def redirect(url: str, status_code: int = 302, headers: Mapping[str, str] | None = None) -> RedirectResponse:
    return RedirectResponse(url, status_code=status_code, headers=headers)

def abort(status_code) -> HTMLResponse:
    return HTMLResponse(status_code=status_code)

def authenticate(scheme="bearer") -> Callable:
    return get_instance().authenticate(scheme)

_services : dict[str, App] = {}
def get_instance(name: str = "") -> App:
    if name not in _services:
        _services[name] = App(name)
    return _services[name]

# class Application(UnrestRouter):
#     def __init__(self, templates=None, pages=None, assets="assets", nocache=True):
#         super().__init__()
#         self.templates = Jinja2Templates(directory=templates, auto_reload=nocache)

#         if os.path.exists(assets):
#             static = StaticFiles(directory=assets)
#             if nocache:
#                 static.is_not_modified = lambda *args, **kwargs: False
#             self.router.mount("/assets", static, name="static")

#         if pages and os.path.exists(pages):
#             # TODO: autogenerate a bunch of get endpoints
#             pass


#     def render(self, template, *args, **kwargs):
#         return self.templates.TemplateResponse(context.request, template, *args, **kwargs)


