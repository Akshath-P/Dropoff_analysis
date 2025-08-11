import pytest
import pandas as pd
import json
import aiofiles
from unittest.mock import patch, MagicMock, AsyncMock

from bi_agents.schemas import ProcessedMetadata  # Make sure this import is correct
from bi_agents.services.metadata_service import (
    get_or_generate_metadata,
    _handle_file_upload,
    _handle_database_server,
    _fetch_data_description,
)
from bi_agents.config import settings


SOURCE_NAME = "test_db.db"
SCHEMA_INFO = {"USERS": ["id", "name"], "ORDERS": ["order_id", "user_id"]}
TABLE_DETAILS = {
    "USERS": {"rows": 100, "columns": 2},
    "ORDERS": {"rows": 500, "columns": 2},
}
HAPPY_PATH_OUTPUT = {
    "description": {
        "title": "test_db.db",
        "metadata": {
            "USERS": {
                "columns": 2,
                "rows": 100,
                "column_info": {"id": "User ID", "name": "User Name"},
            }
        },
    },
    "short_summary": "A short summary.",
    "long_summary": "A long summary.",
}
SAD_PATH_OUTPUT = {
    "description": {
        "title": SOURCE_NAME,
        "metadata": {
            "error": {
                "columns": 0,
                "rows": 0,
                "column_info": {
                    "message": "Metadata generation failed due to a formatting error."
                },
            }
        },
    },
    "short_summary": "Summary could not be generated.",
    "long_summary": "Detailed summary could not be generated due to a formatting error.",
}


@pytest.mark.asyncio
class TestMetadataService:

    @pytest.mark.parametrize(
        "test_name, llm_response_content, expected_output",
        [
            (
                "Happy Path: Correctly formatted JSON",
                json.dumps(HAPPY_PATH_OUTPUT),
                HAPPY_PATH_OUTPUT,
            ),
            (
                "Sad Path: Malformed JSON (trailing comma)",
                '{"key": "value",}',
                SAD_PATH_OUTPUT,
            ),
            (
                "Sad Path: Missing required key",
                '{"description": {}, "short_summary": "s"}',
                SAD_PATH_OUTPUT,
            ),
            (
                "Sad Path: Wrong data type",
                '{"description": {}, "short_summary": 123, "long_summary": "l"}',
                SAD_PATH_OUTPUT,
            ),
            (
                "Sad Path: LLM returns conversational text",
                "I am sorry, I cannot help.",
                SAD_PATH_OUTPUT,
            ),
        ],
    )
    @patch("bi_agents.services.metadata_service.client", new_callable=AsyncMock)
    async def test_fetch_data_description_handles_llm_responses(
        self, mock_openai_client, test_name, llm_response_content, expected_output
    ):
        """Verifies that _fetch_data_description correctly handles various LLM string responses."""
        # Arrange
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.content = llm_response_content

        # Act
        result = await _fetch_data_description(
            source_name=SOURCE_NAME,
            schema_info=SCHEMA_INFO,
            table_details=TABLE_DETAILS,
        )

        # Assert
        if test_name.startswith("Happy Path"):
            try:
                # Can we load the result back into our Pydantic model?
                ProcessedMetadata.model_validate(result)
                # You can also add specific checks for key values if you want
                assert (
                    result["description"]["title"]
                    == expected_output["description"]["title"]
                )
            except Exception as e:
                pytest.fail(f"Happy path result failed Pydantic validation: {e}")
        else:
            # For sad paths, match with fallback dictionary
            assert result == expected_output

    # TODO: Update test for mongodb stored file cache.
    @patch(
        "bi_agents.services.metadata_service.get_collection_details",
        new_callable=AsyncMock,
    )
    @patch(
        "bi_agents.services.metadata_service._handle_file_upload",
        new_callable=AsyncMock,
    )
    async def test_get_or_generate_metadata_cache_miss(
        self, mock_handle_upload, mock_get_details
    ):
        # Arrange: No cached file exists
        collection_id = "new_collection"
        metadata_path = settings.METADATA_DIR / f"{collection_id}.json"
        assert not metadata_path.exists()

        mock_get_details.return_value = {
            "dataSource": "file_upload",
            "dataDetails": {"file_upload": {"paths": ["some/path.csv"]}},
        }
        mock_handle_upload.return_value = {"description": {"title": "newly generated"}}

        # Act
        result = await get_or_generate_metadata(collection_id, refresh=True)

        # Assert
        assert result["description"]["title"] == "newly generated"
        mock_get_details.assert_awaited_with(collection_id)
        mock_handle_upload.assert_awaited_once()
        assert metadata_path.exists()

    async def test_get_or_generate_metadata_cache_hit(self):
        # Arrange: A cached file already exists
        collection_id = "existing_collection"
        metadata_path = settings.METADATA_DIR / f"{collection_id}.json"
        # Note: The written data must match the Pydantic schema to be valid
        cached_data = {
            "description": {"title": "from cache", "metadata": {}},
            "short_summary": "s",
            "long_summary": "l",
        }
        async with aiofiles.open(metadata_path, "w") as f:
            await f.write(json.dumps(cached_data))

        # Act
        with patch(
            "bi_agents.services.metadata_service.get_collection_details"
        ) as mock_get_details:
            result = await get_or_generate_metadata(collection_id, refresh=False)
            # Assert
            assert result["description"]["title"] == "from cache"
            mock_get_details.assert_not_called()

    @patch(
        "bi_agents.services.metadata_service.azure_handler.fetch_blob_to_local",
        new_callable=AsyncMock,
    )
    @patch(
        "bi_agents.services.metadata_service.client", new_callable=AsyncMock
    )  # Patch the client now
    async def test_handle_file_upload_csv(
        self, mock_openai_client, mock_azure, tmp_path
    ):
        # Arrange
        csv_path = tmp_path / "test.csv"
        pd.DataFrame({"colA": [1, 2], "colB": ["x", "y"]}).to_csv(csv_path, index=False)
        mock_azure.return_value = str(csv_path)

        # We expect the LLM to return a valid structure
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.content = json.dumps(HAPPY_PATH_OUTPUT)

        file_details = {"paths": ["container/test.csv"]}

        # Act
        result = await _handle_file_upload(file_details, "123")

        # Assert
        assert result["description"]["title"] == "test_db.db"
        assert result["short_summary"] == "A short summary."
        mock_azure.assert_awaited_with("test.csv", settings.DATA_DIR)
        mock_openai_client.chat.completions.create.assert_awaited_once()

        # We can also check the prompt that was sent to the LLM
        sent_prompt = mock_openai_client.chat.completions.create.call_args.kwargs[
            "messages"
        ][0]["content"]
        assert '"rows": 2' in sent_prompt
        assert '"columns": 2' in sent_prompt
        assert '"column_names": [\n      "colA",\n      "colB"\n    ]' in sent_prompt

    @patch(
        "bi_agents.services.metadata_service.aiomysql.connect", new_callable=AsyncMock
    )
    @patch("bi_agents.services.metadata_service.client", new_callable=AsyncMock)
    async def test_handle_database_server(self, mock_openai_client, mock_connect):
        # Arrange
        mock_details = {
            "host": "localhost",
            "dbName": "mockdb",
            "user": "root",
            "password": "pw",
        }
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.content = json.dumps(HAPPY_PATH_OUTPUT)

        mock_cursor = AsyncMock()
        mock_cursor.fetchall.side_effect = [
            [("table1",)],  # Result for "SHOW TABLES"
            [("id",), ("name",)],  # Result for "DESCRIBE `table1`"
        ]
        mock_cursor.fetchone.return_value = (100,)  # Result for "SELECT COUNT(*)"

        mock_conn = AsyncMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Act
        result = await _handle_database_server(mock_details, "456")

        # Assert
        assert result["description"]["title"] == "test_db.db"
        mock_connect.assert_awaited_once()
        mock_openai_client.chat.completions.create.assert_awaited_once()

        # Check the prompt sent to the LLM
        sent_prompt = mock_openai_client.chat.completions.create.call_args.kwargs[
            "messages"
        ][0]["content"]
        assert '"table1"' in sent_prompt
        assert '"rows": 100' in sent_prompt
        assert '"columns": 2' in sent_prompt
        assert '"column_names": [\n      "id",\n      "name"\n    ]' in sent_prompt
