from typing import Literal
from pydantic import BaseModel, Field

class ChosenTool(BaseModel):
    tool_name: Literal['None', "VectorStore"] = Field(description="the tool that was chosen by LLM in question routing stage")