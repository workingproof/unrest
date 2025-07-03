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


class JsonSerialisable:
    def serialise(self) -> dict | list | int | float | str | bool | None:
        raise NotImplementedError("Subclasses must implement this method.")

class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, JsonSerialisable):
            return obj.serialise()
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Record):
            return dict(obj)
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M")
        if isinstance(obj, date):
            return obj.strftime("%Y-%m-%d")
        return super().default(obj)


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
                return json.dumps(content, cls=JSONEncoder)
            else:
                return content.model_dump_json()

        if type(content) is list:
            return ("[%s]" % ",".join([_enc(x) for x in content])).encode("utf-8")
        else:
            return _enc(content).encode("utf-8")


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
