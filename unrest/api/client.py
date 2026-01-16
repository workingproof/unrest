from httpx import ASGITransport, AsyncClient

from unrest import Payload
from starlette.routing import Router


class Client(AsyncClient):
    def __init__(self, app: Router | str):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if isinstance(app, str):
            AsyncClient.__init__(self, base_url=app, headers=headers)
        else:
            AsyncClient.__init__(self, transport=ASGITransport(app=app), base_url="http://test.app", headers=headers)

    async def query(self, path, payload=None, **kwargs):
        if payload is not None:
            if isinstance(payload, Payload):
                kwargs["json"] = payload.model_dump()
            else:
                kwargs["json"] = payload
            return await self.request("QUERY", path, **kwargs)
        return await self.get(path, **kwargs)

    async def mutate(self, path, payload=None, **kwargs):
        if payload is not None:
            if isinstance(payload, Payload):
                kwargs["json"] = payload.model_dump()
            else:
                kwargs["json"] = payload
        return await self.post(path, **kwargs)
