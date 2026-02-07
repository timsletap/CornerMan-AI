from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class MessageResponse(BaseModel):
    message: str


class PaginationParams(BaseModel):
    skip: int = 0
    limit: int = 20
