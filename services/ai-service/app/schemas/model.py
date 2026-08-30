from pydantic import BaseModel


class ModelOut(BaseModel):
    id: str
    name: str
    description: str
