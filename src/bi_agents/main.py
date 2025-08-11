import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routers import router as api_router
from .database.mongo_handler import db_handler
from .config import settings
from .devtools.logging_config import SQLiteHandler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code
    app_logger = logging.getLogger("bi_agents")

    yield

    db_handler.close()
    logging.getLogger("bi_agents.main").info("MongoDB connection closed.")


root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Create a standard formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

db_log_handler = SQLiteHandler(db_path=settings.LOGS_DB_PATH)
db_log_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Set the logger for our package
app_logger = logging.getLogger("bi_agents")
app_logger.setLevel(logging.INFO)
app_logger.addHandler(db_log_handler)
app_logger.addHandler(console_handler)

# Prvent logs from being passed up to root logger
app_logger.propagate = False

# Set log level for autogen events to 'WARNING' or higher
logging.getLogger("autogen_core").setLevel(logging.WARNING)


app = FastAPI(
    title="bi-agents",
    description="A backend service for data analysis using Autogen Agents.",
    version="1.0.0",
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(api_router, prefix="/api")


@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to the bi-agents API"}
