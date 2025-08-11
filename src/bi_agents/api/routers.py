from fastapi import APIRouter, HTTPException
from .models import PromptInput, AnalysisResult, CollectionInput, MetadataResult
from ..services import analysis_service, metadata_service

router = APIRouter()


@router.get("/health", tags=["Health"])
def health():
    return {"status": "Ok"}


@router.post("/fetch_metadata", response_model=MetadataResult, tags=["Metadata"])
async def fetch_metadata(collection_input: CollectionInput):
    try:
        metadata = await metadata_service.get_or_generate_metadata(
            collection_input.collectionId, collection_input.refresh
        )
        return MetadataResult(
            description=metadata.get("description", {}),
            short_summary=metadata.get("short_summary", ""),
            long_summary=metadata.get("long_summary", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", response_model=AnalysisResult, tags=["Analysis"])
async def analyze(prompt_input: PromptInput):
    try:
        result = await analysis_service.run_analysis(prompt_input)
        return result
    except Exception as e:
        # Add more specific error handling
        raise HTTPException(
            status_code=500, detail=f"An error occurred during analysis: {e}"
        )
