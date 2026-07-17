from typing import Literal

from pydantic import BaseModel


class IngestionRetryRequest(BaseModel):
    mode: Literal["AUTO", "REEMBED"] = "AUTO"
