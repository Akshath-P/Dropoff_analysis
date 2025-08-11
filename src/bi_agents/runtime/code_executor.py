import logging

from pathlib import Path
from venv import EnvBuilder
from autogen_ext.code_executors.local import LocalCommandLineCodeExecutor

from ..config import settings

logger = logging.getLogger("bi_agents.runtime.code_executor")


def initialize_code_executor() -> LocalCommandLineCodeExecutor:
    """
    Initializes and prepares the local code executor in a virtual environment.

    TO-DO:
    - Check if required libraries are installed already.
    """
    logger.info("Initializing LocalCommandLineCodeExecutor...")

    # Ensure the virtual environment exists
    # venv_builder = EnvBuilder(with_pip=True)
    # venv_context = venv_builder.ensure_directories(settings.VENV_DIR)

    local_executor = LocalCommandLineCodeExecutor(work_dir=settings.TEMP_CODES_DIR)

    logger.info(f"Executor instantiated with existing environment {settings.VENV_DIR}")

    return local_executor


def initialize_request_code_executor(request_dir: str) -> LocalCommandLineCodeExecutor:
    """
    Initializes and prepares the local code executor in a virtual environment.

    TO-DO:
    - Check if required libraries are installed already.
    """
    # print("Initializing LocalCommandLineCodeExecutor...")

    # Ensure the virtual environment exists
    # venv_builder = EnvBuilder(with_pip=True)
    # venv_context = venv_builder.ensure_directories(settings.VENV_DIR)

    # local_executor = LocalCommandLineCodeExecutor(
    #     work_dir=request_dir, virtual_env_context=venv_context
    # )

    local_executor = LocalCommandLineCodeExecutor(work_dir=request_dir)

    logging.info(f"Executor instantiated with existing environment {request_dir}")

    return local_executor
