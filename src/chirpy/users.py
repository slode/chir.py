import uuid
import bcrypt

from pydantic import BaseModel, Field

from chirpy.types import UserId, shortuuid


class User(BaseModel):
    id: UserId = Field(default_factory=shortuuid)
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool = False
    scopes: str | None = None


class DBUser(BaseModel):
    user: User
    hashed_password: bytes


class UserManager:
    def __init__(self) -> None:
        self.users: dict[UserId, DBUser] = {}

    def create_user(self, user: User, plain_password: str) -> User:
        self.users[user.id] = DBUser(
            user=user, hashed_password=self._get_password_hash(plain_password)
        )
        return user

    def get_user(self, userid: UserId) -> User:
        db_user = self.users[userid]
        return db_user.user

    def get_user_by_name(self, username: str) -> User:
        db_user = self._get_user_by_name(username)
        return db_user.user

    def _get_user_by_name(self, username: str) -> DBUser:
        for db_user in self.users.values():
            if db_user.user.username == username:
                return db_user
        raise KeyError()

    def _verify_password(self, plain_password: bytes, hashed_password: bytes) -> bool:
        return bcrypt.checkpw(plain_password, hashed_password)

    def _get_password_hash(self, plain_password: str) -> bytes:
        return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt())

    def get_authenticated_user(self, username: str, password: str) -> User:
        db_user = self._get_user_by_name(username)

        if db_user is None or not self._verify_password(password.encode(), db_user.hashed_password):
            raise KeyError()

        return db_user.user
