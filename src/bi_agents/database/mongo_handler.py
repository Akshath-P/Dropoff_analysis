import logging

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import InvalidName
from bson import ObjectId
from datetime import datetime
from typing import Dict, List, Optional, Any, TYPE_CHECKING

from ..config import settings

from ..schemas import costlog

if TYPE_CHECKING:
    from ..agents.team_builder import SelectorGroupChat

logger = logging.getLogger("bi_agents.database.mongo_handler")


# --- Database Client ---
class MongoDBHandler:
    def __init__(self, uri: str, max_pool_size: int = 100):
        self.client = AsyncIOMotorClient(uri, maxPoolSize=max_pool_size)
        self.db = self.client["test"]

    def get_collection(self, collection_name: str):
        return self.db[collection_name]

    def close(self):
        self.client.close()


db_handler = MongoDBHandler(settings.MONGODB_URI)


# --- Data Source Logic ---
async def get_collection_details(collection_id: str) -> Optional[Dict]:
    """
    Fetches the data source configuration document from MongoDB asynchronously.
    """

    collections_collection = db_handler.get_collection("collections")

    try:
        # Convert string to ObjectId. Handle potential errors.
        record_id = ObjectId(collection_id)
    except InvalidName:
        logger.error(f"Invalid collectionId format: {collection_id}")
        return None

    try:
        document = await collections_collection.find_one({"_id": record_id})

        if not document:
            logger.info(f"Document with ID {collection_id} not found.")
            return None

        return document
    except Exception as e:
        # Log the full error for better debugging
        logger.error(
            f"An unexpected error occurred while fetching collection details for {collection_id}: {e}"
        )
        return None

async def log_cost_event(cost_log: costlog):
    cost_collection = db_handler.get_collection("cost")
    try:
        log_data = cost_log.model_dump()
        await cost_collection.insert_one(log_data)
        logger.info(f"Successfully logged cost for service '{cost_log.service}'.")
    except Exception as e:
        logger.error(f"Failed to log cost event for {cost_log.collection_ID}: {e}")


async def update_metadata(collection_id: str, data_to_set: Dict):
    collections_collection = db_handler.get_collection("collections")

    try:
        record_id = ObjectId(collection_id)
    except InvalidName:
        print(f'Invalid collectionId format for update:{collection_id}')
        return None

    try:
        result = await collections_collection.update_one(
            {"_id": record_id},
            {"$set": data_to_set}
        )
    
        if result.modified_count >0:
            print(f"Successfully updated metadata for collection: {collection_id}")

        else: print(f"No document with ID {collection_id} was found, or there was no data to update")

        return result
    except Exception as e:
        print(f"An error occurred while updating collection {collection_id}: {e}")
        return None
        


    except Exception as e:
        # Log the full error for better debugging
        logger.error(
            f"An unexpected error occurred while fetching collection details for {collection_id}: {e}"
        )
        return None


# --- Conversation Store ---
class ConversationStore:
    def __init__(self, handler: MongoDBHandler):
        self.team_state_collection = handler.get_collection("team_state")
        self.turn_history_collection = handler.get_collection("turn_history")

    def state_compression(self, data: dict) -> dict:
        """Compresses agent states to reduce memory footprint."""
        for agent_name, agent_data in data.get("agent_states", {}).items():
            if "message_buffer" in agent_data:
                agent_data["message_buffer"] = []
        return data

    async def save_team_state(self, conversation_id: str, team: "SelectorGroupChat"):
        state_data = await team.save_state()
        state_data_compressed = self.state_compression(
            state_data
        )  ## Temporarily disabled.
        # state_data_compressed = state_data
        session_data = {
            "team_state": state_data_compressed,
            "last_activity": datetime.now().isoformat(),
        }
        await self.team_state_collection.update_one(
            {"_id": conversation_id},
            {"$set": {"data": session_data}},
            upsert=True,
        )
        logger.info(f"Team state for conversation {conversation_id} saved.")

    async def load_team_state(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        session_document = await self.team_state_collection.find_one(
            {"_id": conversation_id}
        )
        return (
            session_document.get("data", {}).get("team_state")
            if session_document
            else None
        )

    async def add_turn_to_history(self, conversation_id: str, turn_data: Dict):
        turn_data["conversationId"] = conversation_id
        turn_data["timestamp"] = datetime.now()
        await self.turn_history_collection.insert_one(turn_data)
        logger.info(f"Turn history for conversation {conversation_id} added.")

    async def get_conversation_history(
        self, conversation_id: str, limit: int
    ) -> List[Dict]:
        cursor = (
            self.turn_history_collection.find({"conversationId": conversation_id})
            .sort("timestamp", 1)
            .limit(limit)
        )
        return [doc async for doc in cursor]


conversation_store = ConversationStore(db_handler)
