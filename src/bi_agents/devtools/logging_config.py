import logging
import sqlite3
from pathlib import Path


# Custom handler to write logs to SQLite file
class SQLiteHandler(logging.Handler):
    """
    A logging handler that writes records to a SQLite3 database.
    LOCAL DEVELOPMENT ONLY.
    """

    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        # `check_same_thread=False` for FastAPI
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                logger_name TEXT,
                level TEXT,
                message TEXT,
                exc_text TEXT
            )
        """
        )
        self.conn.commit()

    def emit(self, record: logging.LogRecord):
        """
        This method is called by the logging framework to handle a log record.
        """
        # Format the exception text
        exc_text = None
        if record.exc_info:
            exc_text = logging.Formatter().formatException(record.exc_info)

        # The main log message is formatted by log-handler formatter
        log_message = self.format(record)

        sql = """
            INSERT INTO logs (timestamp, logger_name, level, message, exc_text)
            VALUES (?, ?, ?, ?, ?)
        """
        params = (record.asctime, record.name, record.levelname, log_message, exc_text)
        self.cursor.execute(sql, params)
        self.conn.commit()

    def close(self):
        """
        Closes the database connection.
        """
        self.conn.close()
        super().close()
