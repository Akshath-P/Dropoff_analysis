import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure the path is correct based on your pytest.ini (`pythonpath = . src`)
from bi_agents.services.analysis_service import run_analysis, _process_chat_results
from bi_agents.api.models import PromptInput
from bi_agents.config import settings


@pytest.mark.asyncio
class TestAnalysisService:
    """
    Tests the core business logic of the analysis service.
    Mocks all external dependencies like database access and AI model calls.
    """

    # Use targeted patching for each async method that will be awaited.
    # This is more robust than patching the entire parent object.
    @patch(
        "bi_agents.services.analysis_service.get_or_generate_metadata",
        new_callable=AsyncMock,
    )
    @patch(
        "bi_agents.services.analysis_service.agent_team_manager.get_or_create_team",
        new_callable=AsyncMock,
    )
    @patch(
        "bi_agents.services.analysis_service.conversation_store.get_conversation_history",
        new_callable=AsyncMock,
    )
    @patch(
        "bi_agents.services.analysis_service.conversation_store.add_turn_to_history",
        new_callable=AsyncMock,
    )
    @patch(
        "bi_agents.services.analysis_service.conversation_store.save_team_state",
        new_callable=AsyncMock,
    )
    @patch("bi_agents.services.analysis_service.client", new_callable=AsyncMock)
    async def test_run_analysis_pipeline(
        self,
        mock_openai_client,
        mock_save_state,
        mock_add_history,
        mock_get_history,
        mock_get_or_create_team,
        mock_get_metadata,
    ):
        """
        Verifies the end-to-end orchestration of the run_analysis function,
        ensuring all dependencies are called correctly.
        """
        # --- Arrange ---
        # 1. Configure the mocks' return values
        mock_get_metadata.return_value = {"description": "some metadata"}
        mock_get_history.return_value = []  # Simulate no previous conversation history

        # Mock the Autogen agent team and its execution result
        mock_team = AsyncMock()
        mock_chat_result = MagicMock()
        mock_chat_result.messages = [
            MagicMock(content="Some intermediate agent message...", models_usage=None),
            MagicMock(
                content='```json\n{"long_summary": "Detailed agent summary", "executable_code": "print(\'analysis code\')"}\n```',
                models_usage=MagicMock(prompt_tokens=50, completion_tokens=100),
            ),
        ]
        mock_team.run.return_value = mock_chat_result
        mock_get_or_create_team.return_value = mock_team

        # Mock the final summarization call to the OpenAI client
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "Final concise summary."

        # 2. Create the input payload for the service function
        prompt_input = PromptInput(
            prompt="What are the sales trends?",
            collectionId="collection-123",
            conversationId="conversation-abc",
        )

        # --- Act ---
        # Execute the function under test
        result = await run_analysis(prompt_input)

        # --- Assert ---
        # Verify that each dependency was called with the correct arguments
        mock_get_metadata.assert_awaited_with("collection-123", refresh=False)
        mock_get_or_create_team.assert_awaited_with("conversation-abc")
        mock_get_history.assert_awaited_with(
            "conversation-abc", limit=settings.MESSAGE_HISTORY_LIMIT
        )

        # Check that the agent team was executed
        mock_team.run.assert_awaited_once()

        # Check that the conversation turn was saved to history
        mock_add_history.assert_awaited_with(
            "conversation-abc",
            {
                "user_request": "What are the sales trends?",
                "agent_summary": "Detailed agent summary",
            },
        )

        # Check that the agent team's state was persisted
        mock_save_state.assert_awaited_with("conversation-abc", mock_team)

        # Verify the final output is structured correctly
        assert result.final_summary == "Final concise summary."
        assert result.long_summary == "Detailed agent summary"
        assert result.code == "print('analysis code')"
        assert result.token == 150  # 50 prompt + 100 completion

        # Ensure the temporary directory for the request was created and then cleaned up
        assert len(list(settings.TEMP_CODES_DIR.iterdir())) == 0

    def test_process_chat_results_success(self):
        """
        Tests the helper function that parses the final JSON block from the agent's output.
        """
        # Arrange
        mock_chat_result = MagicMock()
        mock_chat_result.messages = [
            MagicMock(content="Some other message"),
            MagicMock(
                content='Here is the final result: ```json\n{"long_summary": "The summary is correct.", "executable_code": "final_code"}\n```'
            ),
            MagicMock(
                content="TERMINATE"
            ),  # The parser should search backwards and find the JSON
        ]

        # Act
        result = _process_chat_results(mock_chat_result)

        # Assert
        assert result["long_summary"] == "The summary is correct."
        assert result["executable_code"] == "final_code"
        assert "error" not in result

    def test_process_chat_results_no_json(self):
        """

        Tests the edge case where the agent fails to produce a structured JSON output.
        """
        # Arrange
        mock_chat_result = MagicMock(
            messages=[MagicMock(content="I am unable to complete the request.")]
        )

        # Act
        result = _process_chat_results(mock_chat_result)

        # Assert
        assert "No structured JSON output found" in result["error"]
        assert "The agent did not produce a final summary." in result["long_summary"]

    def test_process_chat_results_invalid_json(self):
        """
        Tests the edge case where the agent produces a malformed JSON block.
        """
        # Arrange
        malformed_json_string = '```json\n{"long_summary": "summary", "executable_code": "code",}\n```'  # Extra comma
        mock_chat_result = MagicMock(
            messages=[MagicMock(content=malformed_json_string)]
        )

        # Act
        result = _process_chat_results(mock_chat_result)

        # Assert
        assert "Invalid JSON from agent" in result["error"]
        assert "The agent produced invalid JSON" in result["long_summary"]
