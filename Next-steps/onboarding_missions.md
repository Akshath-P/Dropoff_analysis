`# 🚀 Engineering Onboarding Missions

Welcome, Agent. Your onboarding begins with four high-priority missions. Each one is tailored to introduce you to a critical area of our platform — testing, API design, cost tracking, and prompt architecture. You are not alone — your mission lead will assist you as you explore the codebase, set up your tools, and deploy your first changes.

---

# Mission Brief 1: Test Ops Specialist

### **Your Role:**

As our Test Ops Specialist, your focus is on the resilience and reliability of the platform. You'll work to fortify our application's defenses by expanding our automated test suite, ensuring that our core logic is verified and protected against future changes.

### Primary Objective (Weeks 1 & 2):

Enhance the unit test coverage for the metadata\_service, specifically targeting the data ingestion and processing pathways.

### Key Intel (Files for Reconnaissance):

- `src/bi_agents/services/metadata_service.py`: The target file. Analyze the \_handle\_file\_upload (for CSV/SQLite) and \_handle\_database\_server functions.
- `tests/test_services/test_metadata_service.py`: Your starting point. Contains existing tests that serve as examples.
- `tests/conftest.py`: The central configuration for our test environment. Note how it mocks external services to isolate our code during tests.

### Core Skills to Deploy:

- **Pytest:** Our testing framework. Understand test function structure (def test\_...) and the assert statement.
- **Mocking (unittest.mock):** The technique of replacing live dependencies with controlled fakes. You'll use AsyncMock to simulate async functions.
- **Asyncio Testing:** The @pytest.mark.asyncio decorator is key for testing asynchronous code.

### Tactical Approach (Suggested Execution Plan):

1. **System Check:** Run pytest from the terminal. A full pass of existing tests confirms your environment is operational.
2. **Target Analysis:** In \_handle\_file\_upload, identify the distinct logic paths for .csv and .sqlite files. These are your primary test cases.
3. **First Engagement (CSV Path):**
   - In test\_metadata\_service.py, define a new test: async def test\_handle\_file\_upload\_csv\_path():.
   - Within the test, mock the function's dependencies (azure\_handler.fetch\_blob\_to\_local, OpenAI client).
   - Simulate a CSV file being "downloaded" and assert that the function correctly parses its schema and passes the correct information to the mocked OpenAI client.
4. **Second Engagement (SQLite Path):**
   - Define async def test\_handle\_file\_upload\_sqlite\_path():.
   - This time, you will need to mock aiosqlite.connect to simulate a database connection and its responses.
5. **Expand Operations:** If time permits, apply the same pattern to test the \_handle\_database\_server function, mocking the aiomysql library.

### Success Conditions (Definition of 'Done'):

- At least two new, passing test functions are committed to test\_metadata\_service.py.
- The new tests explicitly validate the logic for both CSV and SQLite file handling.
- AsyncMock is used effectively to isolate the functions from external network calls.
- The entire test suite (pytest) runs successfully without errors.

### Bonus Objective (Stretch Goal):

- Investigate pytest.mark.parametrize. Can you use it to consolidate testing for both a "success" case and a "failure" case (e.g., a malformed file) into a single, more efficient test function?

---

# Mission Brief 2: API Design Specialist

### **Your Role:**

As our API Design Specialist, you are responsible for the clarity and usability of our application's primary interface. Your mission is to refine the API's "contract" to make it self-documenting, intuitive for other developers, and resilient to invalid data.

### Primary Objective (Weeks 1 & 2):

Enhance all API data models using Pydantic Field to provide rich, automatic documentation and validation.

### Key Intel (Files for Reconnaissance):

- `src/bi_agents/api/models.py`: Your primary operational area. This file defines the data structures for all API inputs and outputs.
- `src/bi_agents/main.py`: The entry point for the application. You'll run this with uvicorn.
- **Browser-based Interface:** After starting the server, navigate to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). This interactive API documentation is the direct output of your work.

### Core Skills to Deploy:

- **Pydantic:** Specifically, the Field function for adding metadata and validation rules to model properties.
- **API Design Principles:** Understanding why clear examples, descriptions, and validation are critical for a good API.
- **FastAPI Internals:** How FastAPI leverages Pydantic models to generate an OpenAPI schema.

### Tactical Approach (Suggested Execution Plan):

1. **Establish a Baseline:** Run the application and examine the /docs page. Note the lack of descriptions and examples in the API schemas. This is your "before" state.
2. **Initial Modification:** In `src/bi_agents/api/models.py`, import Field from the pydantic library. Locate the PromptInput model. Modify the prompt field from `prompt: str` to:

```python
prompt: str = Field(
    ...,
    description="The natural language query for the agent to analyze.",
    example="What were the top 5 performing products last quarter?",
    min_length=10
)
```

3. **Verify the Impact:** The uvicorn server will auto-reload. Refresh the /docs page. Observe how the schema for PromptInput is now enriched with your description and example.
4. **System-wide Rollout:** Apply this pattern to every property in every model within api/models.py. Ensure each has a clear description and a useful example. Add validation rules (min\_length, gt=0, etc.) where logical.
5. **Continuous Verification:** Periodically check the /docs page throughout the process to see your improvements live.

### Success Conditions (Definition of 'Done'):

- Field is imported and used for every property in api/models.py.
- Every property includes a professional description and a realistic example.
- At least three distinct validation rules are implemented across the models.
- The auto-generated API documentation at /docs is clear, detailed, and useful.

### Bonus Objective (Stretch Goal):

- Explore custom validation with Pydantic's @validator decorator. Can you write a validator for the collectionId field that ensures it contains no illegal characters (like spaces or slashes)?

---

# Mission Brief 3: Ops Analyst

### **Your Role:**

As our Ops Analyst, you integrate critical operational metrics into the platform. Technology has real-world costs, and your mission is to provide the business intelligence needed to track and manage our AI resource consumption by implementing accurate cost-per-analysis calculations.

### Primary Objective (Weeks 1 & 2):

Implement a robust cost calculation utility based on OpenAI token usage and integrate it into the analysis service.

### Key Intel (Files for Reconnaissance):

- `src/bi_agents/services/analysis_service.py`: The run\_analysis function is where token counts are currently calculated. This is where you will integrate your work.
- `src/bi_agents/api/models.py`: The AnalysisResult model contains the cost: float field you will be populating.
- **External Intel Source:** The official OpenAI API pricing webpage. You will need to source the latest token costs for models like gpt-4o-mini.

### Core Skills to Deploy:

- **Code Organization:** Creating new, organized Python modules for reusable logic.
- **Utility Function Design:** Writing clean, single-purpose functions.
- **External Data Integration:** Finding and correctly applying external information (pricing data) in your code.

### Tactical Approach (Suggested Execution Plan):

1. **Locate Data Source:** In analysis\_service.py, find the token calculation logic at the end of the run\_analysis function (prompt\_tokens, completion\_tokens). These are your inputs.
2. **Gather Intelligence:** Research and document the current input and output token costs for the gpt-4o-mini model from OpenAI's official site.
3. **Establish a Calculation Module:** To maintain clean architecture, create a new utility module: src/bi\_agents/utils/cost\_calculator.py. In this new file, define a function: `def calculate_cost(prompt_tokens: int, completion_tokens: int, model_name: str) -> float:`. Implement the logic inside this function to calculate the total cost based on the token counts and the pricing you researched.
4. **Integrate the Module:** In analysis\_service.py, import your new function: `from ..utils.cost_calculator import calculate_cost`. Find the line `cost=0` and replace it with a call to your new utility: `cost=calculate_cost(prompt_tokens, completion_tokens, prompt_input.model)`.
5. **Confirm Functionality:** Run a full analysis through the API and inspect the JSON response. Verify that the cost field is no longer 0 and displays a correct, non-zero value.

### Success Conditions (Definition of 'Done'):

- The new module src/bi\_agents/utils/cost\_calculator.py is created and implemented.
- The module contains a function that accurately calculates API costs.
- The run\_analysis service function successfully uses this new utility.
- The /api/analyze endpoint returns responses with a correctly calculated cost.

### Bonus Objective (Stretch Goal):

- Make your calculate\_cost function more scalable. Instead of hardcoding prices, define a dictionary within the module that maps multiple model names (gpt-4o-mini, gpt-4o, etc.) to their respective input/output costs. The function can then look up the correct price based on the model\_name parameter.

---

# Mission Brief 4: Prompt Architect

### **Your Role:**

As our Prompt Architect, you are responsible for organizing the core instructions we provide to our AI agents. A well-structured prompt library is essential for maintainability, experimentation, and readability. Your mission is to centralize our agent prompts into a dedicated, reusable library.

### Primary Objective (Weeks 1 & 2):

Refactor all hardcoded, multi-line prompts from the service layer into a new, dedicated prompt management module.

### Key Intel (Files for Reconnaissance):

- `src/bi_agents/services/analysis_service.py`: Contains a large f-string prompt within the \_prepare\_agent\_prompt function.
- `src/bi_agents/services/metadata_service.py`: Contains another large f-string prompt within the \_fetch\_data\_description function.

### Core Skills to Deploy:

- **Modular Programming:** Understanding how to organize code into logical modules and import them where needed.
- **Software Design Principles:** Applying the principle of "Separation of Concerns" to separate application logic from prompt content.
- **String Templating:** Using f-strings or other templating methods to inject variables into text.

### Tactical Approach (Suggested Execution Plan):

1. **Identify First Target:** Locate the large f-string assigned to description\_prompt in metadata\_service.py. This is your first artifact to archive.
2. **Construct the Library:** Create a new file: src/bi\_agents/prompts.py.
3. **Archive the First Prompt:** In prompts.py, define a function that encapsulates the prompt:

```python
def get_metadata_generation_prompt(source_name: str, schema_info: dict) -> str:
    # Copy the entire f-string from metadata_service.py into this function.
    # Ensure all variables like {source_name} are passed as arguments.
    prompt_template = f"""
    You are an expert data analyst...
    ... for the data source named '{source_name}'.
    ...
    """
    return prompt_template
```

4. **Link the Library:** In metadata\_service.py, import the new module: `from .. import prompts`. Replace the entire multi-line f-string block with a clean, single-line call to your new function: `description_prompt = prompts.get_metadata_generation_prompt(source_name, input_schema_for_llm)`.
5. **Verify and Repeat:** Run the application and confirm the metadata generation feature works identically. Once verified, repeat this entire process for the prompt located in analysis\_service.py.

### Success Conditions (Definition of 'Done'):

- The new module src/bi\_agents/prompts.py exists and is in use.
- The large, hardcoded prompts have been completely removed from the service files.
- The prompts.py module contains functions that build and return the required prompt strings.
- The service files now import and call these prompt-generating functions.
- The end-to-end functionality of the application remains unchanged.

### Bonus Objective (Stretch Goal):

- Research a more advanced templating engine like Jinja2 (which is what FastAPI itself uses). Consider refactoring one of your prompt functions to use a Jinja2 template loaded from a separate .txt file. This provides an even cleaner separation of code and content.

---

4 different freshers, 4 missions, one for each, fcfs

