from pydantic import BaseModel, Field, RootModel
from typing import Dict, Optional, Literal
from datetime import datetime

# Pydantic models for dataset metadata.
class ColumnInfo(RootModel[Dict[str, str]]):
    """A dictionary mapping column names to their descriptions."""

    pass


class TableMetadata(BaseModel):
    """Detailed metadata for a single table within the data source."""

    columns: int = Field(..., description="The total number of columns in the table.")
    rows: int = Field(..., description="The total number of rows in the table.")
    column_info: Dict[str, str] = Field(
        ...,
        description="A dictionary mapping each column name to a concise, one-line description of its purpose.",
    )
    data_head: Optional[str] = Field(
        None,
        description="An optional string representation of the first few rows of the table's data.",
    )


class Description(BaseModel):
    """The structured description of the entire data source."""

    title: str = Field(
        ...,
        description="The name of the data source (e.g., filename or database name).",
    )
    metadata: Dict[str, TableMetadata]


class ProcessedMetadata(BaseModel):
    """
    Represents the fully processed and validated metadata for a data source,
    including a deeply structured description and LLM-generated summaries.
    This is a core data structure used across multiple services.
    """

    description: Description = Field(
        ..., description="A detailed, structured description of the data source."
    )
    short_summary: str = Field(
        ..., description="A concise, 2-3 line executive summary of the data's purpose."
    )
    long_summary: str = Field(
        ...,
        description="A more detailed 5-6 line summary emphasizing relationships and use cases.",
    )
    # cost: Optional[Dict[str,float]] = Field(
    #     default= None,
    #     description = "The detailed cost + token usage breakdown for the metadata"
    # )

# A new schema to log costs
class costlog(BaseModel):
    timestamp: datetime = Field(default_factory= datetime.now)
    collectionId: str = Field(
        ...,
        description= "The ID of the collection being accessed"                      
    )
    userId: str = Field(
        ...,
        description="The ID of the user making the query"
    )
    conversationId: Optional[str] = Field(
        default= None,
        description= "Conversation ID, if the action was analysis"
    )
    requestId: Optional[str] = Field(
        default = 'None',
        description= 'The request ID of the query'
    )
    service: Literal["Metadata", "analysis"] = Field(
        ...,
        Description= "The service that incurred the cost"
    )
    costDetails: Dict[str,float] = Field(
        ...,
        description= "The cost incurred by the analysis"
    )


class AgentOutput(BaseModel):
    """
    Defines the expected JSON structure for the consultant agent's final output.
    This acts as a strict contract for validation.
    """

    long_summary: str = Field(
        ...,
        description="A detailed, multi-paragraph summary of the agent's findings, including key numerical insights.",
    )
    code: str = Field(
        ...,
        description="A string containing the final, clean Python code block that produced the results.",
    )


class RelevanceResponse(BaseModel):
    """
    Defines the expected JSON structure for the domain gatekeeper's response.
    """

    response: Literal["yes", "no"]
    reason: str
