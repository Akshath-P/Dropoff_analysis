import pytest
from unittest.mock import patch, AsyncMock
from bi_agents.api.models import AnalysisResult, MetadataResult


@pytest.mark.asyncio
class TestApiEndpoints:
    def test_health(self, api_client):
        response = api_client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "Ok"}

    @patch(
        "bi_agents.api.routers.metadata_service.get_or_generate_metadata",
        new_callable=AsyncMock,
    )
    async def test_fetch_metadata_success(self, mock_get_metadata, api_client):
        # Arrange
        mock_get_metadata.return_value = {
            "description": {"table": "info"},
            "short_summary": "short",
            "long_summary": "long",
        }
        payload = {"collectionId": "123", "refresh": False}

        # Act
        response = api_client.post("/api/fetch_metadata", json=payload)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == {"table": "info"}
        assert data["short_summary"] == "short"
        mock_get_metadata.assert_awaited_with("123", False)

    @patch(
        "bi_agents.api.routers.metadata_service.get_or_generate_metadata",
        new_callable=AsyncMock,
    )
    async def test_fetch_metadata_error(self, mock_get_metadata, api_client):
        # Arrange
        mock_get_metadata.side_effect = ValueError("Collection not found")
        payload = {"collectionId": "999", "refresh": True}

        # Act
        response = api_client.post("/api/fetch_metadata", json=payload)

        # Assert
        assert response.status_code == 500
        assert "Collection not found" in response.json()["detail"]

    @patch(
        "bi_agents.api.routers.analysis_service.run_analysis", new_callable=AsyncMock
    )
    async def test_analyze_success(self, mock_run_analysis, api_client):
        # Arrange
        mock_result = AnalysisResult(
            final_summary="Final answer.",
            chart=[],
            long_summary="Longer agent summary.",
            code="print('hello')",
            token=100,
            cost=0,
            model="gpt-4o-mini",
        )
        mock_run_analysis.return_value = mock_result
        payload = {"prompt": "Analyze", "collectionId": "123", "conversationId": "456"}

        # Act
        response = api_client.post("/api/analyze", json=payload)

        # Assert
        assert response.status_code == 200
        assert response.json()["final_summary"] == "Final answer."
        mock_run_analysis.assert_awaited_once()
