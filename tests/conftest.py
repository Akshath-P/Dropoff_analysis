import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from pathlib import Path

# This works because of `pythonpath = . src` in pytest.ini
from bi_agents.main import app
from bi_agents.config import settings


@pytest.fixture(scope="session")
def api_client():
    """A TestClient for making requests to the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_settings(tmp_path: Path):
    """
    Automatically mocks the global settings object for every test,
    redirecting all file I/O to a temporary directory.
    """
    with patch.object(settings, "TEMP_CODES_DIR", tmp_path / "tempcodes"), patch.object(
        settings, "STATIC_DIR", tmp_path / "static"
    ), patch.object(settings, "DATA_DIR", tmp_path / "data"), patch.object(
        settings, "METADATA_DIR", tmp_path / "metadata"
    ), patch.object(
        settings, "LOGS_DB_PATH", tmp_path / "logs.db"
    ):

        settings.TEMP_CODES_DIR.mkdir(exist_ok=True)
        settings.STATIC_DIR.mkdir(exist_ok=True)
        settings.DATA_DIR.mkdir(exist_ok=True)
        settings.METADATA_DIR.mkdir(exist_ok=True)
        yield


@pytest.fixture(autouse=True)
def mock_external_services():
    """
    Automatically mocks all external service clients for every test.
    This prevents any real network calls to OpenAI, Azure, or databases.
    """
    # Patch the clients where they are instantiated in the new structure
    with patch(
        "bi_agents.services.metadata_service.client", new_callable=AsyncMock
    ) as mock_openai_metadata, patch(
        "bi_agents.services.analysis_service.client", new_callable=AsyncMock
    ) as mock_openai_analysis, patch(
        "bi_agents.storage.azure_handler.BlobServiceClient", new_callable=MagicMock
    ) as mock_blob_service, patch(
        "bi_agents.database.mongo_handler.AsyncIOMotorClient", new_callable=MagicMock
    ) as mock_mongo_client, patch(
        "bi_agents.services.metadata_service.aiomysql", new_callable=AsyncMock
    ) as mock_aiomysql, patch(
        "bi_agents.services.metadata_service.aiosqlite", new_callable=AsyncMock
    ) as mock_aiosqlite:

        # Configure the mock for azure_handler to return an async-compatible client
        mock_blob_service.from_connection_string.return_value = AsyncMock()

        yield {
            "openai_metadata": mock_openai_metadata,
            "openai_analysis": mock_openai_analysis,
            "blob_service": mock_blob_service,
            "mongo_client": mock_mongo_client,
            "aiomysql": mock_aiomysql,
            "aiosqlite": mock_aiosqlite,
        }
