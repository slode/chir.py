import base64
import uuid

from typing import NewType

SHOID = NewType("SHOID", str)


def shortuuid() -> str:
    return uuid.uuid4().hex[:8]


MessageId = NewType("MessageId", str)
SessionId = NewType("SessionId", str)
UserId = NewType("UserId", str)
