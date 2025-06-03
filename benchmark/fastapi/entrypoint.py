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


@app.get("/static", response_model=ExampleResponse)
async def get_static(user: Optional[dict] = Depends(get_user)):
    return ExampleResponse(id="123", email="foo@bar.com")

@app.get("/random", response_model=ExampleResponse)
async def get_random(session: SessionDep, user: Optional[dict] = Depends(get_user)):
    return session.exec(select(users).order_by("id").limit(1)).first()
    