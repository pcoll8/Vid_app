"""
Logging Configuration
Provides structured logging with WebSocket broadcast support
"""

import logging
import sys
from datetime import datetime
from typing import Callable, Optional, List
from queue import Queue
import json


class WebSocketLogHandler(logging.Handler):
    """Custom handler that queues log messages for WebSocket broadcast"""
    
    _instances: List['WebSocketLogHandler'] = []
    
    def __init__(self):
        super().__init__()
        self.log_queue: Queue = Queue(maxsize=1000)
        WebSocketLogHandler._instances.append(self)
    
    def emit(self, record: logging.LogRecord):
        try:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "message": self.format(record),
                "module": record.module
            }
            if self.log_queue.full():
                try:
                    self.log_queue.get_nowait()
                except Exception:
                    pass
            self.log_queue.put_nowait(log_entry)
        except Exception:
            self.handleError(record)
    
    def get_logs(self, max_count: int = 100) -> List[dict]:
        """Get queued logs without blocking"""
        logs = []
        while not self.log_queue.empty() and len(logs) < max_count:
            try:
                logs.append(self.log_queue.get_nowait())
            except:
                break
        return logs
    
    @classmethod
    def get_all_logs(cls, max_count: int = 100) -> List[dict]:
        """Get logs from all instances"""
        all_logs = []
        for instance in cls._instances:
            all_logs.extend(instance.get_logs(max_count))
        return all_logs


# Global WebSocket handler instance
ws_handler: Optional[WebSocketLogHandler] = None


def setup_logger(name: str = "viralclip", level: int = logging.INFO) -> logging.Logger:
    """Set up and configure the application logger"""
    global ws_handler
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(module)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # WebSocket handler for real-time log streaming
    ws_handler = WebSocketLogHandler()
    ws_handler.setLevel(level)
    ws_format = logging.Formatter("%(message)s")
    ws_handler.setFormatter(ws_format)
    logger.addHandler(ws_handler)
    
    return logger


def get_logger(name: str = "viralclip") -> logging.Logger:
    """Get the configured logger instance"""
    return logging.getLogger(name)


def get_ws_handler() -> Optional[WebSocketLogHandler]:
    """Get the WebSocket log handler"""
    global ws_handler
    return ws_handler
