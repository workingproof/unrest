import inspect
import json
import typing
import sys
from datetime import date, datetime
from typing import Callable, get_args, get_origin

# json
from uuid import UUID

from asyncpg import Record
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import Response
from starlette.exceptions import HTTPException

from unrest.observability import getLogger
from unrest.router import ClientError, UnrestRouter

log = getLogger(__name__)


class Payload(BaseModel):
    pass


class PayloadResponse(Response):
    media_type = "application/json"

    def __init__(
        self,
        content: Payload | list[Payload],
        status_code: int = 200,
        headers: typing.Mapping[str, str] | None = None,
        media_type: str | None = None,
        background: BackgroundTask | None = None,
    ) -> None:
        super().__init__(content, status_code, headers, media_type, background)

    def render(self, content: Payload | list[Payload] | dict | list[dict]) -> bytes:
        def _enc(content):
            if type(content) is dict:
                return json.dumps(content)
            else:
                return content.model_dump_json()

        if type(content) is list:
            return ("[%s]" % ",".join([_enc(x) for x in content])).encode("utf-8")
        else:
            return _enc(content).encode("utf-8")


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Record):
            return dict(obj)
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M")
        if isinstance(obj, date):
            return obj.strftime("%Y-%m-%d")
        return super().default(obj)


class JSONResponse(Response):
    media_type = "application/json"

    def __init__(
        self,
        content: typing.Any,
        status_code: int = 200,
        headers: typing.Mapping[str, str] | None = None,
        media_type: str | None = None,
        background: BackgroundTask | None = None,
    ) -> None:
        super().__init__(content, status_code, headers, media_type, background)

    def render(self, content: typing.Any) -> bytes:
        return json.dumps(content, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":"), cls=JSONEncoder).encode("utf-8")


class ApiRequestHandler(Callable):
    def __init__(self, func: Callable):
        self.func = func
        self.returns = None
        self.payload = None
        self.args = {}
        self.kwargs = {}

        if not inspect.iscoroutinefunction(func):
            raise RuntimeError("Request handlers must be async coroutines")

        def _get_type(annotation):
            if annotation is not None and annotation != inspect.Parameter.empty:
                if get_origin(annotation) is list:
                    args = get_args(annotation)
                    if len(args) == 1 and issubclass(args[0], Payload):
                        return (args[0], True)
                if issubclass(annotation, Payload):
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

    async def __call__(self, req: Request):
        try:
            res = await self.dispatch(req)
            log.info("%s %s %d" % (req.method, req.url, res.status_code))
            return res
        except HTTPException as ex:
            log.info("%s %s %s" % (req.method, req.url, ex.status_code), file=sys.stderr)

    async def dispatch(self, req: Request):
        args = []
        kwargs = {}

        try:
            if self.payload:
                js = await req.json()
                if self.payload[1]:
                    args.append([self.payload[0](**x) for x in js])
                else:
                    args.append(self.payload[0](**js))

            if self.args:
                for k in self.args:
                    args.append(req.path_params.get(k))
            if self.kwargs:
                for k, v in self.kwargs.items():
                    kwargs[k] = req.query_params.get(k, v)
        except Exception:
            raise ClientError()

        resp = await self.func(*args, **kwargs)

        if resp is None:
            return JSONResponse(None, status_code=202)

        if isinstance(resp, Response):
            return resp

        def _maybewrap(obj, payload_class):
            if isinstance(obj, payload_class):
                return obj
            else:
                return payload_class(**dict(obj))

        if self.returns is None:
            return JSONResponse(resp)
        else:
            if self.returns[1]:
                return PayloadResponse([_maybewrap(x, self.returns[0]) for x in resp])
            else:
                return PayloadResponse(_maybewrap(resp, self.returns[0]))


class Api(UnrestRouter):
    def query(self, path) -> Callable:
        def decorator(f: Callable) -> Callable:
            return self._addroute(path, f, True, "POST", ApiRequestHandler(f))

        return decorator

    def mutate(self, path) -> Callable:
        def decorator(f: Callable) -> Callable:
            return self._addroute(path, f, False, "PATCH", ApiRequestHandler(f))

        return decorator

    def get(self, path) -> Callable:
        def decorator(f: Callable) -> Callable:
            return self._addroute(path, f, True, "GET", ApiRequestHandler(f))

        return decorator

    def post(self, path) -> Callable:
        def decorator(f: Callable) -> Callable:
            return self._addroute(path, f, False, "POST", ApiRequestHandler(f))

        return decorator

    def put(self, path) -> Callable:
        def decorator(f: Callable) -> Callable:
            return self._addroute(path, f, False, "PUT", ApiRequestHandler(f))

        return decorator

    def delete(self, path) -> Callable:
        def decorator(f: Callable) -> Callable:
            return self._addroute(path, f, False, "DELETE", ApiRequestHandler(f))

        return decorator

    def abort(self, status_code):
        return JSONResponse(status_code=status_code)
