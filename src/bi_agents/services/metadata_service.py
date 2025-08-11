import json
import asyncio
import os
import logging
import aiosqlite
import pandas as pd
import aiomysql
import aiofiles
from openai import AsyncOpenAI
from typing import Dict, List, Any

from pydantic import ValidationError

from ..config import settings
from ..schemas import ProcessedMetadata, costlog
from ..storage.azure_handler import azure_handler
#importing update_metadata 
from ..database.mongo_handler import get_collection_details, update_metadata, log_cost_event


# importing the calculate_cost function
from ..devtools.cost_calculator import calculate_cost

logger = logging.getLogger("bi_agents.services.metadata_service")

# Initialize the OpenAI client once for the service
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def _fetch_data_description(
    source_name: str,
    schema_info: List[str] | Dict[str, Any],
    table_details: Dict[str, Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Calls the OpenAI API to generate a rich description, a short summary,
    and a long summary for a given data source schema.

    Args:
        source_name: The name of the data source (e.g., blob name, database name).
        schema_info: The schema of the data (list of columns or dict of tables).
        table_details: Dictionary with row and column counts for each table.

    Returns:
        A dictionary containing the generated description, short summary, and long summary.
    """
    input_schema_for_llm = {}

    for table_name, column_list in schema_info.items():
        details = table_details.get(table_name, {})
        input_schema_for_llm[table_name] = {
            "columns": len(column_list),
            "rows": details.get("rows", "unknown"),
            "column_names": column_list,
        }

    # Main prompt to get the detailed column-by-column description in a structured JSON format
    description_prompt = f"""
    You are an expert data analyst. Your task is to create a comprehensive, structured
    JSON metadata object for a given database schema.

    **1. Analyze the Input Schema**
    Here is the raw schema information for the data source named '{source_name}'.
    ```json
    {json.dumps(input_schema_for_llm, indent=2)}
    ```
    **2. Generate the Output JSON:**
    Your response MUST be a single, valid JSON object. Adhere strictly to the following
    structure and instructions.
    ***Instructions for each field:***
    - description.title: Generate a clean, human-readable title for the dataset.
        - **RULE:** Base the title on the core subject of the source name `{source_name}`.
        - **REASON:** This title will be displayed directly to end-users, so it must be professional and easy to read.
        - **DO NOT INCLUDE:**
            - File extensions (e.g., '.csv', '.db', '.sqlite')
            - Timestamps or random numbers (e.g., '1749558303558_').
            - Underscores. Use spaces and proper capitalization instead.
        - **EXAMPLES**
            - If source_name is '1749558303558_top_100_saas_companies_2025.csv', a good title is "Top 100 SaaS Companies 2025".
            - If source_name is 'pjh_sales_db.sqlite', a good title is "PJH Sales Data".
            - If source_name is 'q3_financial_report.csv', a good title is "Q3 Financial Report".
    - description.metadata: This an object where each key is a table name from the input schema.
    - descripton.metadata.TABLE.columns: Copy the number of columns from the input schema.
    - description.metadata.TABLE.rows: Copy the number of rows from the input schema.
    - description.metadata.TABLE.column_info: For each column in the table, write a concise,
        one-line description of it's business purpose. Pay close attention to columns ending in "ID"
        to identify relationships.
    - short_summary: Write a 2-3 line executive summary. Mention key entities and the total number of sales records if available.
    - long_summary: Write a detailed 5-6 line summary. Emphasize the hierarchical relationships between tables
        (e.g., Distributor -> Stockist -> Retailer) and other key information.

    **3. Example output Structure:**
    Your final JSON object must be structured similarly to this example:
    ```json
    {{
        "description": {{
            "title": "database_name.db",
            "metadata": {{
            "TABLE_NAME_1": {{
                "columns": 7,
                "rows": 25,
                "column_info": {{
                "Column1": "Description for column 1.",
                "Column2": "Description for column 2."
                }}
            }}
            }}
        }},
        "short_summary": "A concise 2-3 line summary of the dataset's purpose and key entities.",
        "long_summary": "A detailed 5-6 line summary emphasizing relationships and analytical use cases."
    }}
    ```
    """

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": description_prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    llm_output_str = response.choices[0].message.content
    
    #getting the tokens used from the model itself
    calculated_cost = None
    if response.usage:
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        calculated_cost = calculate_cost(prompt_tokens, completion_tokens, settings.DEFAULT_METADATA_LLM)
        logger.info(f"Metadata generation for '{source_name}' prompt_tokens = {prompt_tokens: .6f}, input_cost = ${calculated_cost['input_cost']: .6f} , completion_tokens = {completion_tokens:.6f}, output_cost = ${calculated_cost['output_cost']: .6f}, total_tokens: {prompt_tokens+completion_tokens: .6f}, total_cost: ${calculated_cost['total_cost']:.6f}")
    try:
        parsed_json = json.loads(llm_output_str)
        validated_data = ProcessedMetadata.model_validate(parsed_json)
        # if calculated_cost:
        #     validated_data.cost = calculated_cost
        # logger.info(
        #     f"Successfully generated and validated metadata for `{source_name}`"
        # )
        metadata_dict = validated_data.model_dump()
        if calculated_cost:
            metadata_dict['cost'] = calculated_cost
        return metadata_dict
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(
            f"Failed to parse or validate LLM response for {source_name}. Error:{e}\nResponse was: {llm_output_str}"
        )

        ## TODO: Try and gracefully exit, notify the frontend of an error and auto retry with a max counter

        # Return a safe, default structure that conforms to the ProcessedMetadata schema
        return {
            "description": {
                "title": source_name,
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


async def _ensure_local_file_from_upload(file_details: dict) -> tuple[str, str]:
    """
    Ensures a file from a 'file_upload' data source is available locally and
    returns its path and type.

    Returns:
        A tuple containing (local_filepath: str, file_type: str).
    """
    if not file_details.get("paths"):
        raise ValueError("No file paths provided in file_upload details.")

    schema_path = file_details["paths"][0]
    blob_name = os.path.basename(schema_path)
    file_extension = blob_name.split(".")[-1].lower()
    local_filepath = os.path.join(settings.DATA_DIR, blob_name)

    if not os.path.exists(local_filepath):
        logger.info(f"Local file not found at {local_filepath}. Fetching from Azure...")
        await azure_handler.fetch_blob_to_local(blob_name, settings.DATA_DIR)
    else:
        logger.info(f"Found local file at {local_filepath}. Skipping download.")

    return local_filepath, file_extension


async def _generate_metadata_from_file(local_filepath: str, file_type: str) -> Dict:
    """
    Generates metadata by parsing a local file (CSV, SQLite, etc.).
    This function is agnostic to the original source of the file.
    """
    source_name = os.path.basename(local_filepath)
    metadata_payload = {}
    if file_type == "csv":
        df = await asyncio.to_thread(pd.read_csv, local_filepath, low_memory=False)
        schema_info_dict = {source_name: df.columns.to_list()}
        table_details_dict = {
            source_name: {"rows": df.shape[0], "columns": df.shape[1]}
        }
        generated_info = await _fetch_data_description(
            source_name, schema_info_dict, table_details_dict
        )
        metadata_payload = {**generated_info}

    elif file_type in {"sqlite", "db"}:
        schema_info = {}
        table_details = {}
        async with aiosqlite.connect(local_filepath) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            )
            tables = [t[0] for t in await cursor.fetchall()]
            await cursor.close()
            for table in tables:
                cursor = await conn.execute(f'PRAGMA table_info("{table}");')
                columns = [col[1] for col in await cursor.fetchall()]
                schema_info[table] = columns
                await cursor.close()
                cursor = await conn.execute(f'SELECT COUNT(*) FROM "{table}";')
                row_count = (await cursor.fetchone())[0]
                table_details[table] = {"rows": row_count, "columns": len(columns)}
                await cursor.close()
        generated_info = await _fetch_data_description(
            source_name, schema_info, table_details=table_details
        )
        metadata_payload = {**generated_info}
    else:
        raise ValueError(f"Unsupported file type for metadata generation: {file_type}")

    return metadata_payload


async def _handle_database_server(database_details: dict, collection_id: str) -> Dict:
    """Processes direct database connections (e.g., MySQL) in a fully non-blocking manner."""
    required_keys = ("host", "dbName", "user", "password")
    if not all(k in database_details for k in required_keys):
        raise ValueError("Incomplete database connection details provided.")

    db_name = database_details["dbName"]
    connection_config = {
        "user": database_details["user"],
        "password": database_details["password"],
        "host": database_details["host"],
        "port": database_details.get("port", 3306),
        "database": db_name,
    }

    schema_info = {}
    table_details = {}
    conn = None

    try:
        conn = await aiomysql.connect(**connection_config)
        cursor = await conn.cursor()
        await cursor.execute("SHOW TABLES")
        tables = [table[0] for table in await cursor.fetchall()]

        for table in tables:
            await cursor.execute(f"DESCRIBE `{table}`")
            columns = [row[0] for row in await cursor.fetchall()]
            schema_info[table] = columns

            await cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            row_count = (await cursor.fetchone())[0]
            table_details[table] = {"rows": row_count, "columns": len(columns)}

    except Exception as err:
        raise ConnectionError(
            f"Failed to connect to or query the MySQL database: {err}"
        )
    finally:
        if cursor:
            await cursor.close()
        if conn:
            conn.close()

    generated_info = await _fetch_data_description(
        db_name, schema_info, table_details=table_details
    )

    return {
        "connection_config": connection_config,  # Store config for agent use
        "file_type": "mysql",
        **generated_info,
    }


async def get_or_generate_metadata(collection_id: str, refresh: bool = False) -> Dict:
    """
    Main service function to retrieve or generate metadata for a collection.
    It guarantees that for file-based sources, the data file exists locally
    before returning, even when serving from cache.
    """
    collection_doc = await get_collection_details(collection_id)
    if not collection_doc:
        raise FileNotFoundError(
            f"Collection with ID {collection_id} not found in the database."
        )

    data_source = collection_doc.get("dataSource")
    data_details = collection_doc.get("dataDetails")

    if not data_source or not data_details:
        raise ValueError(
            "Invalid collection document: missing dataSource or dataDetails."
        )

    if data_source == "file_upload":
        # ALWAYS ensure the local file exists for this data source type.
        local_filepath, file_type = await _ensure_local_file_from_upload(
            data_details.get("file_upload", {})
        )

        # Decide whether to use cache or generate new metadata.
        cached_metadata = collection_doc.get("metaData")
        if not refresh and cached_metadata:
            logger.info(f"Returning cached metadata for collection {collection_id}.")
            # Augment cached data with the guaranteed file path and type.
            cached_metadata["file_path"] = local_filepath
            cached_metadata["file_type"] = file_type
            return cached_metadata
        else:
            logger.info(
                f"Generating new metadata for collection {collection_id}. Refresh: {refresh}"
            )
            # Generate new metadata from the now-guaranteed local file.
            metadata = await _generate_metadata_from_file(local_filepath, file_type)

            cost_object = metadata.pop('cost', None)


            # if metadata:
            #     await update_metadata(collection_id, metadata)
            #     return metadata
            # Add the file path and type for consistency.
            if cost_object:
                user_id_obj = collection_doc.get("userId")
                user_id_str = str(user_id_obj) if user_id_obj else 'unknown user'
                cost_log = costlog(
                    collectionId= collection_id,
                    userId= user_id_str,
                    service= 'Metadata',
                    costDetails= cost_object
                )
                await log_cost_event(cost_log)
            metadata["file_path"] = local_filepath
            metadata["file_type"] = file_type
            return metadata

    elif data_source == "database_server":
        cached_metadata = collection_doc.get("metaData")
        if not refresh and cached_metadata:
            logger.info(f"Returning cached metadata for collection {collection_id}.")
            return cached_metadata
        else:
            logger.info(
                f"Generating new metadata for collection {collection_id}. Refresh: {refresh}"
            )
            metadata = await _handle_database_server(
                data_details.get("database", {}), collection_id
            )

            cost_object = metadata.pop('cost', None)

            # if metadata:
            #     await update_metadata(collection_id, metadata)
            #     return metadata

            if cost_object:
                user_id_obj = collection_doc.get("userId")
                user_id_str = str(user_id_obj) if user_id_obj else 'unknown user'
                cost_log = costlog(
                    collectionId= collection_id,
                    userId= user_id_str,
                    service = 'Metadata',
                    costDetails= cost_object
                )
                await log_cost_event(cost_log)
            return metadata
    else:
        raise NotImplementedError(f"Data source '{data_source}' is not supported.")
