from unrest import db, api, auth, Payload

@db.query
def random():
    return db.fetchrow("select * from users order by random() limit 1")

class ExampleResponse(Payload):
    id: str
    email: str

@api.authenticate("bearer")
async def authenticate_with_api_key(token: str) -> auth.User | None:
    props = await db._fetchrow("select id, email, claims from users where apikey = $1", token)
    if props:
        return auth.AuthenticatedUser(props["id"], props["email"], {}, props["claims"])
    return None

@api.query("/static")
async def get_static() -> ExampleResponse:
    return ExampleResponse(id="123", email="foo@bar.com")

@api.query("/random")
async def get_random() -> ExampleResponse:
    async with random() as result:
        return result


from unrest import Server
server = Server()



