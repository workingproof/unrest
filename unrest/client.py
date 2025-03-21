from httpx import ASGITransport, AsyncClient

from unrest.api import Payload
from unrest.router import UnrestRouter


class Client(AsyncClient):
    def __init__(self, app_or_base_url: UnrestRouter | str = None):
        if type(app_or_base_url) is str:
            AsyncClient.__init__(self, base_url=app_or_base_url)
        elif callable(app_or_base_url):
            AsyncClient.__init__(self, transport=ASGITransport(app=app_or_base_url), base_url="http://test.app")
        else:
            AsyncClient.__init__(self)

    def query(self, path, payload=None, **kwargs):
        if payload is not None:
            if isinstance(payload, Payload):
                kwargs["json"] = payload.model_dump()
            else:
                kwargs["json"] = payload
        return self.post(path, **kwargs)

    def mutate(self, path, payload=None, **kwargs):
        if payload is not None:
            if isinstance(payload, Payload):
                kwargs["json"] = payload.model_dump()
            else:
                kwargs["json"] = payload
        return self.patch(path, **kwargs)
