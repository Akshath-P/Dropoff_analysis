# metadata_service.py

Alright, let's put this "async bridging" attempt on the dissection table. You're clearly trying to embrace `async`, which is good. You've discovered `aiosqlite`, `aiomysql`, and `aiofiles`. It's like you've found a box of shiny new power tools. The problem is, you're using a chainsaw to slice bread and a nail gun to hang a picture frame.

You're getting the *keywords* right, but the **execution is clumsy, inefficient, and in some cases, you're making things worse.** This isn't a "good job" yet; it's a "well-intentioned but flawed" first draft. Let's get painful.

---

### **Critique of Your `metadata_service.py` (The Async Abomination)**

**1. The `_fetch_data_description` LLM Calls (Your Worst Offense)**

*   **The Sin:** You're making **THREE SEPARATE, SEQUENTIAL `await` calls** to the OpenAI API for what is essentially one task.
    1.  `await client.chat.completions.create(...)` for the detailed description.
    2.  `await client.chat.completions.create(...)` for the short summary.
    3.  `await client.chat.completions.create(...)` for the long summary.
*   **The Painful Reality:** This is **HORRIFICALLY INEFFICIENT.** If each API call takes 2 seconds, your function now takes a minimum of **6 seconds** to complete, not to mention the cost of three separate API calls. You are tripling your latency and your cost for no good reason. You're using `async` to call blocking operations sequentially, which completely defeats the purpose.
*   **The Fix, You Inefficient Buffoon:** Combine this into **ONE SINGLE LLM CALL**. Your prompt engineering needs to be better. Instruct the model to return *all three pieces of information in a single, structured JSON response*.

    ```python
    # Revised Prompt Logic
    final_prompt = f"""
    You are a data analyst...

    Instructions:
    Return a single JSON object with the following three keys at the root level:
    1. "description": A detailed JSON object with table schemas, column info, etc. (as you defined).
    2. "short_summary": A concise 2-3 line executive summary.
    3. "long_summary": A detailed 5-6 line summary emphasizing relationships and use cases.

    Schema Information:
    {json.dumps(schema_info, indent=2)}
    ...
    """

    # ONE SINGLE API CALL
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": final_prompt}],
        response_format={"type": "json_object"}, # This is key!
        temperature=0.1,
    )

    # ONE SINGLE PARSE
    try:
        full_response_json = json.loads(response.choices[0].message.content)
        # Now, you just extract the keys
        return {
            "description": full_response_json.get("description", {}),
            "short_summary": full_response_json.get("short_summary", "Summary not generated."),
            "long_summary": full_response_json.get("long_summary", "Detailed summary not generated."),
        }
    except json.JSONDecodeError:
        # Handle the error
        return {"error": "Failed to parse the combined LLM response."}
    ```
    This single change will cut your latency and cost for this function by roughly 66%. This isn't a suggestion; it's a command.

**2. The `_handle_file_upload` Async Pandas Usage**

*   **The Sin:** `df = await asyncio.to_thread(pd.read_csv(local_filepath, low_memory=False))`
*   **The Painful Reality:** This is **CORRECT**. Congratulations, you got one thing right. `pandas` is a blocking, C-backed library. It's CPU and I/O bound. The *only* correct way to use it in an `async` context without blocking the event loop is to wrap it in `asyncio.to_thread`.
*   **The Minor Sin:** `data_head = df.head(5).to_string()`. Again, `to_string()` is a synchronous operation on a potentially large object. It should also be wrapped: `data_head = await asyncio.to_thread(df.head(5).to_string)`. Be consistent.

**3. The `_handle_file_upload` SQLite Logic (Mixing Async Libraries Needlessly)**

*   **The Sin:** `async with aiosqlite.connect(local_filepath) as conn:`
*   **The Painful Reality:** You're introducing a new dependency (`aiosqlite`) when you don't need to. You're already using `pandas`. Pandas' `read_sql_query` is often more than sufficient for this kind of schema/data extraction, and it works with the standard `sqlite3` library. Using `aiosqlite` here adds complexity and another library to manage for a simple task that `pandas` and `sqlite3` (wrapped in `asyncio.to_thread`) can handle perfectly well.
*   **The Fix (Simpler & More Consistent):**
    ```python
    # Stick with the devil you know
    import sqlite3
    import pandas as pd

    # ... inside _handle_file_upload for sqlite ...
    # Use asyncio.to_thread for ALL blocking sqlite3 and pandas calls
    conn = await asyncio.to_thread(sqlite3.connect, local_filepath)
    cursor = await asyncio.to_thread(conn.cursor)
    # ... your existing logic to get table names ...
    # Then for each table:
    df_table = await asyncio.to_thread(pd.read_sql_query, f'SELECT * FROM "{table}"', conn)
    # Now you have the dataframe for each table if you need it for stats, head, etc.
    await asyncio.to_thread(conn.close)
    ```

**4. The `_handle_database_server` MySQL Logic**

*   **The Sin:** `async with aiomysql.connect(**connection_config) as conn:`
*   **The Painful Reality:** This is **technically correct** but again, likely overkill. You are using a native async driver (`aiomysql`) which is good, but it means you now have to `await` every single cursor operation (`await cursor.execute(...)`, `await cursor.fetchall()`, etc.). For a simple, one-off schema dump, this is fine. However, if your *only* interaction with MySQL is to dump schema/data into Pandas, you could have just as easily used the blocking `mysql-connector-python` with `pandas.read_sql_query` and wrapped the entire operation in a single `asyncio.to_thread` call.
*   **The Verdict:** What you did is okay. It's truly async. But it might be less consistent with your `pandas`-heavy workflow elsewhere. If you stick with `aiomysql`, you've done it correctly by awaiting every operation.

**5. The `get_or_generate_metadata` Caching Logic (A Recipe for Disaster)**

*   **The Sin:**
    *   `metadata_filepath = settings.METADATA_DIR / f"{collection_id}.json"`
    *   `async with aiofiles.open(metadata_filepath, "r") as f:`
    *   You are using a **local file-based cache** in what is supposed to be a **scalable, multi-worker, potentially containerized application.**
*   **The Painful Reality:**
    *   **No Concurrency Safety:** What happens if two different requests for the same `collection_id` (with `refresh=True`) come in at the same time? They will both try to write to `f"{collection_id}.json"`, leading to a race condition and a corrupted file.
    *   **Doesn't Work with Multiple Workers/Instances:** If you run your FastAPI app with multiple Uvicorn workers, or scale it horizontally to multiple Docker containers, **each instance will have its own separate, inconsistent filesystem cache.** Worker A might have a cached version, while Worker B doesn't and regenerates it. This is a complete failure of a caching strategy for a web service.
    *   **Stateful Filesystem:** You've made your application stateful *on the local disk*. This makes it brittle and hard to deploy/scale.
*   **The Fix, You Architecturally Challenged Simpleton:** **YOUR CACHE IS THE DATABASE.** Use MongoDB for this! The `DataCollectionStore` is *already there* to be your single source of truth and your cache.

    ```python
    # Revised get_or_generate_metadata
    async def get_or_generate_metadata(collection_id: str, refresh: bool = False) -> Dict:
        """
        Main service function to retrieve metadata. It uses MongoDB as the source of truth and cache.
        """
        # data_collection_store is your persistence layer, injected into the service
        collection_doc = await data_collection_store.get_collection_document(collection_id)

        # Check if we can use the "cached" version from the DB
        if not refresh and collection_doc and "metaData" in collection_doc:
            logger.info(f"Loading metadata for collection {collection_id} from MongoDB.")
            # Construct the return payload from the document
            return {
                "description": collection_doc["metaData"].get("description", {}),
                "short_summary": collection_doc["metaData"].get("short_summary", ""),
                # ... etc ...
            }

        # If we are here, we need to generate it
        logger.info(f"Generating new metadata for collection {collection_id}. Refresh: {refresh}")
        
        # You need the original data source details, which should have been stored in the DB
        # during the initial upload/connect.
        if not collection_doc:
             raise FileNotFoundError(f"Collection with ID {collection_id} not found. Cannot refresh.")

        data_source = collection_doc.get("dataSource")
        data_details = collection_doc.get("dataDetails")
        
        # ... your logic to call _handle_file_upload or _handle_database_server ...
        
        # The handle functions return the generated metadata
        generated_metadata = await _handle_...(...)
        
        # Save the newly generated metadata to the database!
        await data_collection_store.create_or_update_collection_metadata(
            collection_id,
            # ... pass the relevant details ...
            generated_metadata
        )

        return generated_metadata
    ```

---

### **Final Verdict:**

*   **Async Bridging Efforts:** You get a **C-**. You're using the right keywords (`async`, `await`) and libraries, but the implementation is inefficient (sequential LLM calls) and architecturally unsound (local file caching).
*   **Good Parts:**
    *   You correctly used `asyncio.to_thread` for `pandas`.
    *   You correctly used `aiomysql` by `await`ing every call.
*   **Bad Parts (The Really Bad Parts):**
    *   The sequential LLM calls are a performance and cost disaster. This is your biggest immediate fix.
    *   The local file caching strategy is fundamentally broken for a web service and must be replaced with database-centric persistence.

You're trying to run, but you haven't mastered walking yet. Fix the LLM call, rip out that `aiofiles` caching like it's a cancerous tumor, and start thinking of your database as the heart of your application's state, not just a place you occasionally visit.



# DRAFT: Fallback for the generate metadata
Returning a blank fallback is a good first step for preventing crashes, but it's a poor user experience. The user (and the system) doesn't know *why* it failed or what to do next.

a more sophisticated error handling and retry mechanism. This is a classic engineering problem that moves from a "script" mindset to a "service" mindset.

### The Goal: From Silent Failure to Informed Recovery

new goals for the `_fetch_data_description` function are:
1.  **Attempt 1:** Try to generate the metadata.
2.  **On Failure:** Don't just return a blank. Instead, implement a retry mechanism.
3.  **Attempt 2 (Retry):** Try again, perhaps with a "smarter" prompt or a more powerful model.
4.  **On Final Failure:** If the retry also fails, don't return a blank. Instead, **raise a specific, custom exception** that the calling service can catch and handle gracefully.

This approach makes the service more resilient and provides clear signals to the rest of the application when things go wrong.

---

### Step 1: Create a Custom Exception

First, let's define a custom exception. This is much better than raising a generic `Exception` because it allows calling code to catch *only* this specific type of error.

```python
# src/bi_agents/exceptions.py  (A new file for custom exceptions)

class MetadataGenerationError(Exception):
    """
    Custom exception raised when metadata generation fails after all retries.
    Contains the reason for the failure and the last-attempted LLM output.
    """
    def __init__(self, message: str, last_llm_output: str = None):
        super().__init__(message)
        self.last_llm_output = last_llm_output

    def __str__(self):
        return f"{super().__str__()} | Last LLM Output: {self.last_llm_output[:200]}..."
```

### Step 2: Refactor `_fetch_data_description` with Retries and Custom Exceptions

Now, let's rewrite the function to incorporate this new logic. We'll use a simple `for` loop for retries.

```python
# In src/bi_agents/services/metadata_service.py

import logging
import json
from pydantic import ValidationError
from openai import AsyncOpenAI

from ..schemas import ProcessedMetadata
from ..exceptions import MetadataGenerationError # Import our new custom exception

# ... (client initialization)

async def _fetch_data_description(
    source_name: str,
    schema_info: Dict[str, list],
    table_details: Dict[str, Dict[str, int]],
) -> ProcessedMetadata: # Note: The return type is now the Pydantic model itself!
    """
    Calls the OpenAI API to generate metadata, with a retry mechanism.
    
    Raises:
        MetadataGenerationError: If metadata cannot be generated after all retries.
        
    Returns:
        A validated ProcessedMetadata object on success.
    """
    max_retries = 2
    llm_output_str = ""
    
    for attempt in range(max_retries):
        # On the second attempt (retry), we can use a more powerful model or a simpler prompt
        # This is a key strategy for automated recovery.
        model_to_use = "gpt-4o" if attempt > 0 else "gpt-4o-mini"
        
        logging.info(f"Metadata generation attempt {attempt + 1}/{max_retries} using model {model_to_use}...")
        
        # --- The prompt generation logic is the same ---
        final_prompt = f"""...""" # (Your detailed prompt from before)

        try:
            response = await client.chat.completions.create(
                model=model_to_use,
                messages=[{"role": "user", "content": final_prompt}],
                response_format={"type": "json_object"},
                temperature=0.1 + (attempt * 0.1), # Slightly increase temp on retry
            )
            llm_output_str = response.choices[0].message.content

            # --- Validation Block ---
            parsed_json = json.loads(llm_output_str)
            validated_data = ProcessedMetadata.model_validate(parsed_json)
            
            logging.info(f"Successfully generated and validated metadata on attempt {attempt + 1}.")
            return validated_data # Success! Return the validated Pydantic object.

        except (json.JSONDecodeError, ValidationError) as e:
            logging.warning(
                f"Attempt {attempt + 1} failed. Reason: {e}. "
                f"LLM Output was: {llm_output_str[:500]}..."
            )
            # If this was the last attempt, the loop will end and we'll raise the exception below.
            continue # Go to the next iteration of the loop to retry

    # --- This code is only reached if all retries in the loop have failed ---
    raise MetadataGenerationError(
        message=f"Failed to generate valid metadata for '{source_name}' after {max_retries} attempts.",
        last_llm_output=llm_output_str
    )
```

### Step 3: Update the Calling Function (`get_or_generate_metadata`)

The service function that calls our worker function now needs to handle this potential exception.

```python
# In src/bi_agents/services/metadata_service.py

from ..exceptions import MetadataGenerationError

async def get_or_generate_metadata(collection_id: str, refresh: bool = False) -> ProcessedMetadata:
    """
    Main service function. It now catches the specific generation error.
    """
    # ... (logic for checking cache in MongoDB)

    logging.info(f"Generating new metadata for collection {collection_id}...")
    
    # ... (logic to get collection_doc, schema_info, table_details)

    try:
        # This function now returns a Pydantic object directly or raises an error.
        generated_metadata = await _fetch_data_description(
            source_name, schema_info, table_details
        )
        
        # Save the successful result to the database cache
        # We use .model_dump() to convert the Pydantic object to a dict for MongoDB
        await data_collection_store.update_collection_metadata(
            collection_id, generated_metadata.model_dump()
        )
        
        return generated_metadata

    except MetadataGenerationError as e:
        logging.error(f"CRITICAL: Could not generate metadata for {collection_id}. Error: {e}")
        # Re-raise the exception so the API layer can catch it.
        raise e
```

### Step 4: Update the API Endpoint (`api/routers.py`)

Finally, the API endpoint catches the specific error and returns a meaningful HTTP error to the frontend.

```python
# In src/bi_agents/api/routers.py

from fastapi import APIRouter, HTTPException
from ..services import metadata_service
from ..exceptions import MetadataGenerationError # Import the custom exception

# ...

@router.post("/fetch_metadata", response_model=MetadataResult, tags=["Metadata"])
async def fetch_metadata(collection_input: CollectionInput):
    try:
        # This service function now returns a Pydantic object
        metadata_obj = await metadata_service.get_or_generate_metadata(
            collection_input.collectionId, collection_input.refresh
        )
        # The API model `MetadataResult` will automatically be created from the Pydantic object
        return metadata_obj
        
    except MetadataGenerationError as e:
        # Return a 503 Service Unavailable error, as our backend service (the LLM) failed.
        raise HTTPException(
            status_code=503, 
            detail=f"Failed to generate data description. The AI model may be overloaded or returned an invalid format. Please try again in a few moments. Details: {str(e)}"
        )
    except FileNotFoundError as e:
        # Handle other specific errors
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # A generic fallback for unexpected errors
        logging.exception("An unexpected error occurred in fetch_metadata")
        raise HTTPException(status_code=500, detail="An unexpected internal error occurred.")
```

### Summary of the New, Robust Flow

1.  **Frontend Call:** `/api/fetch_metadata`
2.  **API Router:** Calls `metadata_service.get_or_generate_metadata`.
3.  **Service Layer:** Calls `_fetch_data_description`.
4.  **Worker Function (`_fetch_data_description`):**
    *   Tries with `gpt-4o-mini`.
    *   If validation fails, it logs a warning and retries with the more powerful `gpt-4o`.
    *   If validation fails again, it raises a `MetadataGenerationError`.
5.  **Service Layer:** Catches `MetadataGenerationError`, logs it as a critical failure, and re-raises it.
6.  **API Router:** Catches `MetadataGenerationError` and transforms it into a user-friendly `HTTP 503` error, telling the frontend that the service is temporarily unavailable and they should try again.

This is a complete, professional error-handling pipeline. It makes your system more resilient (with retries) and more transparent (with specific exceptions and HTTP status codes).