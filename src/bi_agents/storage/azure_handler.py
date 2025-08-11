import os
import logging
import aiofiles
from azure.storage.blob.aio import BlobServiceClient
from ..config import settings

logger = logging.getLogger("bi_agents.storage.azure_handler")


class AzureBlobHandler:
    def __init__(self, conn_str: str, container_name: str):
        self.blob_service_client = BlobServiceClient.from_connection_string(conn_str)
        self.container_name = container_name

    async def fetch_blob_to_local(self, blob_name: str, local_dir: str) -> str:
        """Downloads a blob to a local directory if it doesn't already exist."""
        local_filepath = os.path.join(local_dir, blob_name)
        if not os.path.exists(local_filepath):
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, blob=blob_name
            )
            async with blob_client:
                stream = await blob_client.download_blob()
                data = await stream.readall()
                async with aiofiles.open(local_filepath, "wb") as download_file:
                    await download_file.write(data)

            logging.getLogger("bi_agents.storage.azure_handler").info(
                f"Downloaded blob {blob_name} to {local_filepath}"
            )
        return local_filepath


azure_handler = AzureBlobHandler(
    settings.AZURE_STORAGE_CONNECTION_STRING, settings.AZURE_CONTAINER_NAME
)
