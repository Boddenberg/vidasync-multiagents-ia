from pydantic import BaseModel, Field


class OrchestrateRequest(BaseModel):
    query: str = Field(min_length=1)


class OrchestrateResponse(BaseModel):
    result: str
