import logging
from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor

from ..config import settings

logger = logging.getLogger("bi_agents.services.runtime.docker_code_executor")


def create_docker_executor(request_dir: str) -> DockerCommandLineCodeExecutor:
    """
    Initializes and prepares the Docker code executor.
    This executor runs code inside a Docker container, providing isolation.
    """
    logger.info("Initializing DockerCommandLineCodeExecutor...")

    docker_executor = DockerCommandLineCodeExecutor(
        image="sandbox-executor:latest",
        work_dir=request_dir,
        timeout=60,
    )

    logger.info(
        f"Docker executor instantiated. It will use the '{docker_executor._image}' image."
    )
    logger.info(
        f"Host directory '{request_dir}' will be mounted to '/workspace' in the container."
    )

    return docker_executor
