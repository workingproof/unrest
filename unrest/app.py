import inspect
import os

from starlette.responses import HTMLResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from unrest import context
from unrest.router import Callable, Request, UnrestRouter


class ApplicationRequestHandler(Callable):
    def __init__(self, func: Callable):
        self.func = func
        self.args = {}
        self.kwargs = {}

        sig = inspect.signature(func)
        for p in sig.parameters.values():
            if p.default is not p.empty:
                self.kwargs[p.name] = p.default
            else:
                self.args[p.name] = None

    async def __call__(self, req: Request):
        args = []
        kwargs = {}
        form = {}

        if req.method == "POST":
            try:
                form = await req.form()
            except:  # noqa
                pass

        for k in self.args:
            args.append(req.path_params.get(k))
        for k, v in self.kwargs.items():
            kwargs[k] = req.query_params.get(k, form.get(k, v))

        resp = await self.func(*args, **kwargs)
        if resp is None:
            return HTMLResponse(status_code=202)
        else:
            return resp


class Application(UnrestRouter):
    def __init__(self, templates=None, pages=None, assets="assets", nocache=True):
        super().__init__()
        self.templates = Jinja2Templates(directory=templates, auto_reload=nocache)

        if os.path.exists(assets):
            static = StaticFiles(directory=assets)
            if nocache:
                static.is_not_modified = lambda *args, **kwargs: False
            self.router.mount("/assets", static, name="static")

        if pages and os.path.exists(pages):
            # TODO: autogenerate a bunch of get endpoints
            pass

    def get(self, path) -> Callable:
        def decorator(f: Callable) -> Callable:
            return self._addroute(path, f, True, "GET", ApplicationRequestHandler(f))

        return decorator

    def post(self, path) -> Callable:
        def decorator(f: Callable) -> Callable:
            return self._addroute(path, f, False, "POST", ApplicationRequestHandler(f))

        return decorator

    def render(self, template, *args, **kwargs):
        return self.templates.TemplateResponse(context.request, template, *args, **kwargs)

    def redirect(self, *args, **kwargs):
        return RedirectResponse(*args, **kwargs)

    def abort(self, status_code):
        return HTMLResponse(status_code=status_code)
