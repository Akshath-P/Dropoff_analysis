from typing import Sequence, Optional, Dict, Any
from openai import OpenAI
import logging

from autogen_core.models import ChatCompletionClient
from autogen_agentchat.agents import AssistantAgent, CodeExecutorAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.messages import BaseChatMessage, BaseAgentEvent
from autogen_core.memory import ListMemory
from autogen_agentchat.messages import StructuredMessage
from autogen_ext.code_executors.local import LocalCommandLineCodeExecutor

from ..config import settings
from ..schemas import AgentOutput
from ..database.mongo_handler import ConversationStore

logger = logging.getLogger("bi_agents.agents.team_builder")


class AgenticTeam:
    """
    A manager class for creating, configuring, and retrieving Autogen agent teams.
    """

    def __init__(
        self,
        conversation_store: ConversationStore,
    ):
        self.conversation_store = conversation_store
        self.model_client = ChatCompletionClient.load_component(
            {
                "provider": "OpenAIChatCompletionClient",
                "config": {
                    "model": settings.DEFAULT_MODEL,
                    "api_key": settings.OPENAI_API_KEY,
                },
            }
        )

    def selector_func(
        self, messages: Sequence[BaseAgentEvent | BaseChatMessage]
    ) -> str | None:
        """Determines the next agent to speak based on the conversation history."""
        last_message = messages[-1]
        last_speaker = getattr(last_message, "source", None)

        if last_speaker == "user":
            return "code_writer"
        if last_speaker == "code_writer":
            return "code_executor"
        if last_speaker == "code_executor":
            content = str(getattr(last_message, "content", ""))
            if "POSIX exit code: 1" in content or "error" in content.lower():
                return "code_writer"  # Return to writer on error
            return "consultant"
        if last_speaker == "consultant":
            return "report_generator"

        return None  # Default case

    def _create_new_team_object(
        self, code_executor: LocalCommandLineCodeExecutor
    ) -> SelectorGroupChat:
        """Factory method to define and assemble a new agent team."""
        user_memory = ListMemory()

        code_writer_agent = AssistantAgent(
            name="code_writer",
            system_message="""
You are a highly experienced, autonomous data scientist. Your primary mission is to answer the user's question by performing a deep and thorough data analysis.

**Core Principles:**
1.  **Break Down Problems:** Deconstruct every question into a series of smaller, solvable steps. For a database, this means: connect, discover tables, inspect schemas, formulate queries, and then analyze results.
2.  **Full Autonomy:** You must perform all analysis steps you formalize from start to finish. Do not stop to ask for human input.
3.  **Insight-Driven:** Your most important output is the numerical insights you derive. Always use `print()` statements to report these findings for the consultant agent.
4.  **Dataset Grounding:** Base all answers, analyses, and insights strictly on the provided dataset.
5.  **Dataset Timeline:** All references to date and time are within the context of the data and not related to current time or date (do not use a now() function in any context)
6.  **Currency:** Assume currency is in INR and use the Indian numbering system for referring to numbers.

**Your Workflow:**
1.  Thoroughly analyze the user's question and the provided data schema.
2.  Write Python code using pandas, scikit-learn, and statsmodels to perform calculations and analysis.
3.  Always present a chart or multiple charts if necessary, regardless of if the outcome is trivial, you must definitely stick to the technical guidelines below.
4.  Always present at least one chart.

---
**CRITICAL TECHNICAL SPECIFICATIONS**
These are not optional. You must follow these rules exactly.

**1. File Saving:**
   - You MUST save all generated files (CSVs, JSON charts) directly into the current working directory.
   - **DO NOT create any subdirectories.**
   - All filenames MUST be prefixed with a number (e.g., `1_data.csv`, `1_chart.json`).

**2. Chart.js JSON Format:**
   - If you create a chart, the JSON file MUST be a valid Chart.js configuration.
   - The `type` property in the JSON MUST be one of these exact strings:
     `["bar", "line", "pie", "scatter", "bubble", "doughnut", "polarArea", "radar"]`
   - The JSON object must follow this general structure:
    ```json
    {
      "type": "line",
      "data": {
        "labels": [],
        "datasets": [{
          "label": "Dataset Label",
          "data": []
        }]
      },
      "options": { ... }
    }
    ```
---
""",
            # 3.  If a visualization is a good way to present the findings, you may generate a chart, but it must follow the strict technical rules below.
            model_client=self.model_client,
            memory=[user_memory],
        )
        code_executor_agent = CodeExecutorAgent(
            name="code_executor",
            description="I execute Python code provided by the code_writer and report back the results or any errors.",
            code_executor=code_executor,
        )
        consultant_agent = AssistantAgent(
            name="consultant",
            system_message="""
            You are a senior data consultant. Your task is to review the entire conversation history, including the final code execution results, and generate a final JSON report.

**Instructions:**
1.  Find the last successfully executed Python code block from the 'code_writer'.
2.  Synthesize all numerical insights and findings from the conversation into an information-dense, multi-paragraph summary.
3.  Your final output MUST be a single, valid JSON object and nothing else. Do not add any text before or after the JSON.
4.  The JSON object must have exactly two keys: "long_summary" and "code".

**Example Output:**
```json
{
    "long_summary": "FULL BLOWN, INFORMATIVE, EXECUTIVE SUMMARY.",
    "code": "CODE BLOCK FOR GENERATING THE RESPONSE NECESSARY FOR INSIGHTS."
}
""",
            model_client=self.model_client,
            memory=[user_memory],
            output_content_type=AgentOutput,
        )
        report_generator_agent = AssistantAgent(
            name="report_generator",
            system_message="Only send the word 'TERMINATE' and nothing else when the consultant has completed the insights report. This marks the end of the workflow.",
            model_client=self.model_client,
        )

        team = SelectorGroupChat(
            participants=[
                code_writer_agent,
                code_executor_agent,
                consultant_agent,
                report_generator_agent,
            ],
            model_client=self.model_client,
            selector_func=self.selector_func,
            allow_repeated_speaker=False,
            termination_condition=TextMentionTermination("TERMINATE")
            | MaxMessageTermination(15),
            custom_message_types=[StructuredMessage[AgentOutput]],
        )
        return team

    async def get_or_create_team(
        self, conversation_id: str, code_executor: LocalCommandLineCodeExecutor
    ) -> SelectorGroupChat:
        """
        Retrieves a team state from the database or creates a new one.
        """
        team = self._create_new_team_object(code_executor=code_executor)

        # Try to load the state from long-term storage (MongoDB)
        saved_state = await self.conversation_store.load_team_state(conversation_id)

        if saved_state:
            logger.info("DEBUG: Found saved state. Attempting to load...")
            try:
                logger.info(
                    f"Loading existing team state for conversation {conversation_id} from database."
                )
                await team.load_state(saved_state)
                logger.info("Successfully loaded team state.")
            except Exception as e:
                logger.error(f"CRASHED during team.load_state()! Error: {e}")
                raise
        else:
            logger.info(f"Creating a new team for conversation {conversation_id}.")

        return team
