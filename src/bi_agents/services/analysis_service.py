import os
import json
import shutil
import re
import uuid
import logging
import aiofiles
from openai import AsyncOpenAI
from typing import Dict, Any, Optional, List

from pydantic import ValidationError

from autogen_agentchat.messages import StructuredMessage
from ..schemas import AgentOutput

from ..config import settings
from ..api.models import PromptInput, AnalysisResult
from ..schemas import AgentOutput, RelevanceResponse, costlog
from ..services.metadata_service import get_or_generate_metadata
from ..agents.team_builder import AgenticTeam
from ..database.mongo_handler import conversation_store, get_collection_details, log_cost_event
from ..runtime.code_executor import initialize_request_code_executor

# importing the calculate cost function
from ..devtools.cost_calculator import calculate_cost

# (Keep existing initializations)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
agent_team_manager = AgenticTeam(conversation_store=conversation_store)
logger = logging.getLogger("bi_agents.services.analysis_service")


# (Keep AgentProcessingError class)
class AgentProcessingError(Exception):
    """Custom exception for failures in processing agent output."""

    def __init__(self, message: str, last_agent_output: str = None):
        super().__init__(message)
        self.last_agent_output = last_agent_output

    def __str__(self):
        if self.last_agent_output:
            return f"{super().__str__()} | Last Agent Output: {self.last_agent_output[:200]}..."
        return super().__str__()


def _prepare_agent_prompt(
    user_prompt: str,
    metadata: Dict[str, Any],
    work_dir: str,
    funnelSteps : List[str],
    data_filename: Optional[str] = None,  # <-- NEW: Add data_filename parameter
) -> str:
    """
    Constructs the detailed, structured prompt for the Autogen team.
    """
    file_access_instruction = ""
    if data_filename:
        file_access_instruction = f"""
        ---
        **CRITICAL DATA ACCESS INSTRUCTIONS**
        The data source for this analysis is a file named '{data_filename}'.
        This file has been placed in your current working directory.
        You MUST connect to it using only its name.

        - For SQLite: `conn = sqlite3.connect('{data_filename}')`
        - For CSV: `df = pd.read_csv('{data_filename}')`

        **DO NOT use any absolute or relative paths (e.g., 'C:\\...', './data/', etc.). Use the filename directly.**
        ---
        """

    prompt = f"""
    You are an expert data scientist. Your task is to provide specialized insights into customer journey and funnel drop-off analysis.

    USER QUESTION: "{user_prompt}"

    CRITICAL FUNNEL INFORMATION: 
    The user has defined stages of the customer's journey with the follwoing columns, in this EXACT order. You MUST use this sequence for your funnel analysis.
    FUNNEL STEPS: {json.dumps(funnelSteps)}

    {file_access_instruction}

    DATA SOURCE METADATA:
    {json.dumps(metadata, indent=2)}

    GUIDELINES:
    1.  Analyze the user's question and the provided data metadata.
    2.  Write Python code to perform the analysis. Use pandas, scikit-learn, and statsmodels.
    3.  For every chart you generate, create a corresponding Chart.js-compatible .json file by referencing a .csv data file.
    4.  Prefix generated files with a number to indicate their order (e.g., '1_chart.json', '1_data.csv', '2_chart.json').

    Begin your analysis.
    """
    return prompt


# (Keep _process_chat_results and _summarize_final_output functions as they are)
def _process_chat_results(chat_result: Any) -> AgentOutput:
    """
    Parses the agent chat history to find the consultant's finala JSON output,
    validates it against the AgentOutput schema, and returns a structured object.

    Raises:
        AgentProcessingError: If the output cannot be found or validated.
    """
    # Search backwards to find the last message from the consultant agent.
    for msg in reversed(chat_result.messages):
        if isinstance(msg, StructuredMessage) and msg.source == "consultant":
            # .content is a validated pydantic object
            if isinstance(msg.content, AgentOutput):
                return msg.content
            else:
                # Safeguard in case the content is of the wrong type (Highly unlikely)
                raise AgentProcessingError(
                    f"Consultant produced a StructuredMessage, but its content was of the wrong type: {type(msg.content).__name__}",
                    last_agent_output=str(msg.content),
                )
    raise AgentProcessingError(
        "The consultant agent did not produce a final structured output message"
    )


async def _summarize_final_output(
    user_prompt: str, agent_summary: str, chart_data: list
) -> str:
    """Generates the final, concise, user-facing summary."""
    llm_prompt = f"""
    Based on the user's original question and the detailed analysis summary provided by a data science agent,
    generate a very short, clear, and simple answer.

    - The answer must be 1-2 sentences long.
    - It must directly answer the user's question.
    - It must use numerical insights from the summary or chart data where possible.
    - If the summary does not contain enough information to answer the question, respond with:
      "I could not find a direct answer to your question in the provided data."

    USER'S QUESTION: "{user_prompt}"

    AGENT'S DETAILED SUMMARY:
    {agent_summary}

    CHART DATA (for numerical reference):
    {json.dumps(chart_data, indent=2)}
    """
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": llm_prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


async def run_analysis(prompt_input: PromptInput) -> AnalysisResult:
    """
    The core analysis pipeline, now with a domain gatekeeper and robust validation.
    """
    request_uuid = str(uuid.uuid4())
    request_work_dir = settings.TEMP_CODES_DIR / str(uuid.uuid4())
    request_work_dir.mkdir(exist_ok=True)

    try:
        metadata = await get_or_generate_metadata(
            prompt_input.collectionId, refresh=False
        )
    
        collection_doc = await get_collection_details(prompt_input.collectionId)
        user_id_str = 'unknown user'
        if collection_doc:
            user_id_obj = collection_doc.get('userId')
            user_id_str = str(user_id_obj) if user_id_obj else 'unknown user'



        data_filename = None
        # Check if the data source is a file that needs to be copied.
        if metadata.get("file_type") in ["csv", "db", "sqlite"]:
            source_filepath = metadata.get("file_path")
            if source_filepath and os.path.exists(source_filepath):
                data_filename = os.path.basename(source_filepath)
                destination_filepath = request_work_dir / data_filename
                logger.info(
                    f"Asynchronously copying {data_filename} to agent workspace..."
                )
                async with aiofiles.open(source_filepath, mode="rb") as src:
                    async with aiofiles.open(destination_filepath, mode="wb") as dest:
                        # TODO For very large files, could read/write in chunks.
                        content = await src.read()
                        await dest.write(content)

                logger.info(
                    f"Successfully copied data file {data_filename} to agent workspace {request_work_dir}"
                )
            else:
                raise FileNotFoundError(
                    f"Data file path not found in metadata or file does not exist: {source_filepath}"
                )

        # Prepare and run the agent team
        async with initialize_request_code_executor(
            request_dir=request_work_dir
        ) as request_executor:
            groupchat = await agent_team_manager.get_or_create_team(
                prompt_input.conversationId, code_executor=request_executor
            )

            task_prompt = _prepare_agent_prompt(
                user_prompt=prompt_input.prompt,
                metadata=metadata,
                work_dir=str(request_work_dir),
                funnel_steps = prompt_input.funnelSteps,
                data_filename=data_filename,
            )
            chat_result = await groupchat.run(task=task_prompt)

        # 5. Process results with the new robust validation
        processed_results = _process_chat_results(chat_result)
        long_summary = processed_results.long_summary
        code = processed_results.code

        # 6. Save conversation state
        turn_data = {"user_request": prompt_input.prompt, "agent_summary": long_summary}
        await conversation_store.add_turn_to_history(
            prompt_input.conversationId, turn_data
        )
        await conversation_store.save_team_state(prompt_input.conversationId, groupchat)

        # 7. Handle generated artifacts
        json_list = []
        # NOTE: The agent is now instructed to save files directly into its working directory.
        # We now look for artifacts in `request_work_dir`.
        for filename in sorted(os.listdir(request_work_dir)):
            if filename.lower().endswith(".json"):
                with open(os.path.join(request_work_dir, filename), "r") as jfile:
                    chart_json = json.load(jfile)
                    chart_json["id"] = str(uuid.uuid4())
                    json_list.append(chart_json)

        # 8. Generate final user-facing summary
        final_summary = await _summarize_final_output(
            prompt_input.prompt, long_summary, json_list
        )

        # 9. Calculate token usage
        prompt_tokens = sum(
            msg.models_usage.prompt_tokens
            for msg in chat_result.messages
            if msg.models_usage
        )
        completion_tokens = sum(
            msg.models_usage.completion_tokens
            for msg in chat_result.messages
            if msg.models_usage
        )
        cost = calculate_cost(prompt_tokens, completion_tokens, prompt_input.model)

        cost_log = costlog(
            collectionId= prompt_input.collectionId,
            userId= user_id_str,
            conversationId= prompt_input.conversationId,
            requestId = request_uuid,
            service = 'analysis',
            costDetails= cost
        )
        await log_cost_event(cost_log)

        return AnalysisResult(
            final_summary=final_summary,
            chart=json_list,
            long_summary=long_summary,
            code=code,
            token=prompt_tokens + completion_tokens,
            calculated_cost=cost,
            model=prompt_input.model,
        )
        

    except AgentProcessingError as e:
        logger.error(f"CRITICAL: AgentProcessingError in run_analysis: {e}")
        return AnalysisResult(
            final_summary="The analysis could not be completed because the AI agent returned an invalid response. Please try rephrasing your question.",
            chart=[],
            long_summary=f"Agent Error: {e}",
            code="Could not extract code due to agent processing error.",
            token=0,
            cost=0,
            model=prompt_input.model,
        )
    except Exception as e:
        logger.exception("An unexpected critical error occurred in run_analysis")
        return AnalysisResult(
            final_summary="An unexpected internal error occurred during the analysis. Please try re-running the analysis.",
            chart=[],
            long_summary=f"An unexpected error occurred: {type(e).__name__}: {e}",
            code="No code available due to an internal error.",
            token=0,
            cost=0,
            model=prompt_input.model,
        )
    finally:
        # 10. Clean up the temporary directory
        if os.path.exists(request_work_dir):
            shutil.rmtree(request_work_dir)
