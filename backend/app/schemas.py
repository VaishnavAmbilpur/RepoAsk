from pydantic import BaseModel, Field
from typing import List, Optional

class CitationModel(BaseModel):
    path: str = Field(description="Exact file path as listed in the repository")
    start_line: int = Field(default=1, description="Starting line number")
    end_line: int = Field(default=1, description="Ending line number")

class RepoAnswerModel(BaseModel):
    title: str = Field(description="Clear document title answering the question, max 8 words")
    short_answer: str = Field(description="1 or 2 sentence direct summary")
    body: str = Field(description="Full markdown body containing sections, explanations, and optional Mermaid flowcharts")
    citations: List[CitationModel] = Field(default_factory=list, description="List of source file citations")

