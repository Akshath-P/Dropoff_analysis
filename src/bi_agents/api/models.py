from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


class PromptInput(BaseModel):
    prompt: str
    collectionId: str
    conversationId: str
    funnelSteps: List[str] = Field(
        ...,
        min_items = 2,
        description= 'Asks the user for different stages in their funnel'
    )
    model: Optional[str] = "gpt-4o-mini"


class CollectionInput(BaseModel):
    collectionId: str
    refresh: bool = Field(default=False)


class AnalysisResult(BaseModel):
    final_summary: str
    chart: List[Dict]
    long_summary: str
    code: Any
    token: float
    calculated_cost: Dict[str,float]
    model: str


class MetadataResult(BaseModel):
    description: Dict
    short_summary: str
    long_summary: str
