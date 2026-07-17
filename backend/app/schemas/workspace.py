import uuid

from pydantic import BaseModel


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    role: str
