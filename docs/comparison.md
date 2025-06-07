# Comparison with FastAPI

We compare **Unrest** with [FastAPI](https://fastapi.tiangolo.com/) -- the most popular modern incumbent in this space -- along two interpretations of "fast":

1. Server performance
2. Developer ergonomics

Our claim is that **Unrest** is superior under both interpretations. 

## Methodology

Develop a minimal, realistic web application in both frameworks:

* A simple database query endpoint with response JSON serialisation
* Token-based user authentication (also via the database)

Note that both frameworks are built on Starlette / Uvicorn and are running the same queries against the same infrastructure. 
Any difference, in performance or ergonomics, is solely attributable to the abstractions provided by either framework.

## Results

### Server performance

Benchmark using [wrk](https://github.com/wg/wrk): 

```
$ wrk -t5 -c10 -d30s --latency \
      -H"Accept: application/json" \
      -H"Authorization: Bearer secretapikey456" \
      http://localhost:8080/random
```

**Unrest** provides a 300% improvement over FastAPI:


|              | Unrest          | FastAPI         |
|:-------------|----------------:|----------------:|
| Latency      | 6.41 ms         | 19.95 ms        |
| Throughput   | 298 KB/s        | 96 KB/s         |
| Requests / s | 1561            | 501             |

Again, this difference in performance is solely attributable to the overhead of abstractions provided by either framework. For FastAPI, that includes an ORM and a dependency injection framework. For Unrest, that includes 
context tracking and enforcement.

### Developer ergonomics

Compare code-listings for each program (provided below)

|              | Unrest          | FastAPI         |
|:-------------|----------------:|----------------:|
| Lines of code| 29              | 48              |
| Characters   | 806             | 1,442           |
| Imports      | 4               | 13              |
| Definitions  | 4               | 9               |

#### Unrest listing

```
from unrest import db, api, auth, Payload

class ExampleResponse(Payload):
    id: str
    email: str

@api.authenticate("bearer")
async def authenticate_with_api_key(token: str) -> auth.User | None:
    props = await db._fetchrow("select id, email, claims from users where apikey = $1", token)
    if props:
        return auth.AuthenticatedUser(props["id"], props["email"], {}, props["claims"])
    return None

@db.query
def random():
    return db.fetchrow("select * from users order by random() limit 1")

@api.query("/random")
async def get_random() -> ExampleResponse:
    async with random() as result:
        return result


from unrest import Server
server = Server()
```

#### FastAPI listing

```
from typing import Annotated, Optional, Union

from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select

class ExampleResponse(BaseModel):
    id: str
    email: str

class users(SQLModel, table=True):
    id: str = Field(primary_key=True)
    email: str = Field()
    apikey: str = Field()

engine = create_engine("postgresql://master:master@localhost:5432/app", echo=False, pool_size=30)
def get_session():
    with Session(engine) as session:
        yield session
SessionDep = Annotated[Session, Depends(get_session)]

app = FastAPI()
security = HTTPBearer()

async def get_user(
    session: SessionDep,
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security),     
) -> Optional[dict]:
    if auth:
        props = session.exec(select(users).where(users.apikey == auth.credentials)).first()
        if props:
            return { "id": props.id, "email": props.email }
    return None

@app.get("/random", response_model=ExampleResponse)
async def get_random(session: SessionDep, user: Optional[dict] = Depends(get_user)):
    return session.exec(select(users).order_by("id").limit(1)).first()
    
```