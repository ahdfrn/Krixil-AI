from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    database: bool
    redis: bool


class ErrorResponse(BaseModel):
    detail: str
