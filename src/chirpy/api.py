import asyncio
import logging
import uuid


from collections import defaultdict
from typing import Annotated, Union, AsyncGenerator
from weakref import WeakSet

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field

from chirpy.users import User, UserManager
from chirpy.types import UserId, MessageId, SessionId, shortuuid
from chirpy import auth, config

logger = logging.getLogger()


class SessionMessage(BaseModel):
    content: str


class SessionInvite(BaseModel):
    user_id: UserId


class Message(BaseModel):
    id: MessageId = Field(default_factory=shortuuid)
    session: SessionId
    origin: User
    message: str
    reply_to: UserId | None = None


class ChatSession(BaseModel):
    id: SessionId = Field(default_factory=shortuuid)
    members: set[UserId] = Field(default_factory=set)
    message_history: list[Message] = Field(default_factory=list)


class Token(BaseModel):
    access_token: str
    token_type: str


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[SessionId, ChatSession] = {}
        self._channels = defaultdict[UserId, WeakSet[asyncio.Queue[Message]]](WeakSet)

    def get_session(self, session_id: SessionId) -> ChatSession:
        return self._sessions.setdefault(session_id, ChatSession(id=session_id))

    def get_user_sessions(self, user_id: UserId) -> list[ChatSession]:
        return [sess for sess in self._sessions.values() if user_id in sess.members]

    async def push_message(self, message: Message) -> None:
        session = self.get_session(message.session)
        session.message_history.append(message)

        for member in session.members:
            for channel in self._channels.get(member, {}):
                await channel.put(message)

    def get_channel(self, user_id: UserId) -> asyncio.Queue:
        queue: asyncio.Queue[Message] = asyncio.Queue()
        self._channels[user_id].add(queue)
        return queue


sessions: SessionManager = SessionManager()


async def get_session_manager() -> SessionManager:
    return sessions


user_manager: UserManager = UserManager()
user_manager.create_user(
    User(
        id=UserId("7a92c202"),
        username="alice",
        full_name="Alice Agent",
        email="alice@chir.py",
        scopes="chat",
    ),
    plain_password="alice",
)
user_manager.create_user(
    User(
        id=UserId("24d58fa9"),
        username="bob",
        full_name="Bobby Bridge",
        email="bob@chir.py",
        scopes="chat:user",
    ),
    plain_password="bob",
)
user_manager.create_user(
    User(
        id=UserId("72b0ed"),
        username="charlie",
        full_name="Charlie Chatbot",
        email="charlie@chir.py",
        scopes="chat",
    ),
    plain_password="charlie",
)


async def get_user_db() -> UserManager:
    return user_manager


app = FastAPI()


@app.exception_handler(Exception)
async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Change here to Logger
    return JSONResponse(
        status_code=500,
        content={
            "message": (
                f"Failed method {request.method} at URL {request.url}."
                f" Exception message is {exc!r}."
            )
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_active_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    users: Annotated[UserManager, Depends(get_user_db)],
) -> User:
    try:
        payload = auth.decode_token(token)
        userid: UserId = payload["id"]
    except (KeyError, auth.TokenValidationException) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user = users.get_user(userid)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")

    return user


@app.post("/token")
async def create_user_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    users: Annotated[UserManager, Depends(get_user_db)],
) -> Token:
    user = users.get_authenticated_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_token(
        payload={"id": user.id, "sub": user.username},
    )
    return Token(access_token=access_token, token_type="bearer")


@app.post("/guest-token")
async def create_guest_token(
    users: Annotated[UserManager, Depends(get_user_db)],
) -> Token:
    user = users.create_user(User(username=f"user-{uuid.uuid4().hex[:4]}"), plain_password="secret")

    access_token = auth.create_token(
        payload={
            "id": user.id,
            "sub": user.username,
        },
    )
    return Token(access_token=access_token, token_type="bearer")


@app.post("/chat")
async def create_chat(
    current_user: Annotated[User, Depends(get_current_active_user)],
    users: Annotated[UserManager, Depends(get_user_db)],
    sessions: Annotated[SessionManager, Depends(get_session_manager)],
) -> ChatSession:
    session = sessions.get_session(SessionId(shortuuid()))
    session.members.add(current_user.id)
    session.members.add(users.get_user_by_name("alice").id)
    session.members.add(users.get_user_by_name("bob").id)
    session.members.add(users.get_user_by_name("charlie").id)

    user_message = Message(
        session=session.id,
        origin=current_user,
        message=f"{current_user.username} created a new session {session.id}",
    )
    await sessions.push_message(user_message)
    return session


@app.delete("/chat")
async def delete_chat(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    return current_user


@app.get("/chat/me")
async def get_chat_me(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    return current_user


@app.get("/chat/me/sessions")
async def get_chat_me_session(
    current_user: Annotated[User, Depends(get_current_active_user)],
    sessions: Annotated[SessionManager, Depends(get_session_manager)],
) -> list[ChatSession]:
    return sessions.get_user_sessions(current_user.id)


@app.post("/chat/{sid}/invite")
async def chat_invite(
    current_user: Annotated[User, Depends(get_current_active_user)],
    sessions: Annotated[SessionManager, Depends(get_session_manager)],
    users: Annotated[UserManager, Depends(get_user_db)],
    invitee: SessionInvite,
    sid: SessionId,
) -> Message:
    if current_user.id not in sessions.get_session(sid).members:
        raise HTTPException(status_code=403, detail="Session not available to user")

    user = users.get_user(invitee.user_id)

    session = sessions.get_session(sid)
    session.members.add(user.id)
    user_message = Message(
        session=sid,
        origin=current_user,
        message=f"{user.username} was invited to the chat by {current_user.username}.",
    )
    await sessions.push_message(user_message)
    return user_message


@app.post("/chat/{sid}/post")
async def chat_post(
    current_user: Annotated[User, Depends(get_current_active_user)],
    sessions: Annotated[SessionManager, Depends(get_session_manager)],
    message: SessionMessage,
    sid: SessionId,
) -> Message:
    if current_user.id not in sessions.get_session(sid).members:
        raise HTTPException(status_code=403, detail="Session not available to user")

    user_message = Message(
        session=sid,
        origin=current_user,
        message=message.content,
    )
    await sessions.push_message(user_message)
    return user_message


async def stream_user_messages(
    user: User, sessions: SessionManager
) -> AsyncGenerator[Union[str, bytes], None]:
    """Stream messages from all subscribed queues"""
    try:
        for session in sessions.get_user_sessions(user.id):
            user_message = Message(
                session=session.id,
                origin=user,
                message=f"{user.username} is listening on session {session.id}",
            )
            await sessions.push_message(user_message)

        queue = sessions.get_channel(user.id)
        while True:
            message: Message = await queue.get()
            yield message.model_dump_json()
            # yield "\n"
    except asyncio.CancelledError:
        ...
    finally:
        for session in sessions.get_user_sessions(user.id):
            user_message = Message(
                session=session.id,
                origin=user,
                message=f"{user.username} is not listening on session {session.id}",
            )
            await sessions.push_message(user_message)


async def format_user_messages(
    user: User, sessions: SessionManager
) -> AsyncGenerator[Union[str, bytes], None]:
    async for message in stream_user_messages(user, sessions):
        yield message
        yield "\n"


@app.get("/chat/listen", response_model=Message)
async def stream_listen_for_messages(
    current_user: Annotated[User, Depends(get_current_active_user)],
    sessions: Annotated[SessionManager, Depends(get_session_manager)],
) -> StreamingResponse:
    return StreamingResponse(format_user_messages(current_user, sessions))


@app.get("/chat/sse", response_model=Message)
async def sse_listen_for_messages(
    current_user: Annotated[User, Depends(get_current_active_user)],
    sessions: Annotated[SessionManager, Depends(get_session_manager)],
) -> StreamingResponse:
    return EventSourceResponse(stream_user_messages(current_user, sessions))


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
    )


if __name__ == "__main__":
    main()
