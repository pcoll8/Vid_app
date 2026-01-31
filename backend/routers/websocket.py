"""
WebSocket Router
Real-time progress updates and log streaming
"""

import asyncio
import json
from typing import Set, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..utils.logger import get_logger, get_ws_handler

router = APIRouter()
logger = get_logger()

# Active WebSocket connections
active_connections: Set[WebSocket] = set()

# Message queues for broadcasting
progress_queue: asyncio.Queue = asyncio.Queue()
log_queue: asyncio.Queue = asyncio.Queue()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time updates"""
    await websocket.accept()
    active_connections.add(websocket)
    logger.info(f"WebSocket connected. Total: {len(active_connections)}")
    
    try:
        # Start background tasks for this connection
        send_task = asyncio.create_task(send_updates(websocket))
        receive_task = asyncio.create_task(receive_messages(websocket))
        
        # Wait for either task to complete (disconnect)
        done, pending = await asyncio.wait(
            [send_task, receive_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        active_connections.discard(websocket)
        logger.info(f"WebSocket removed. Total: {len(active_connections)}")


async def send_updates(websocket: WebSocket):
    """Send queued updates to the WebSocket client"""
    while True:
        try:
            # Check for progress updates
            try:
                progress = progress_queue.get_nowait()
                await websocket.send_json({
                    "type": "progress",
                    "data": progress
                })
            except asyncio.QueueEmpty:
                pass
            
            # Check for log messages
            try:
                log = log_queue.get_nowait()
                await websocket.send_json({
                    "type": "log",
                    "data": log
                })
            except asyncio.QueueEmpty:
                pass
            
            # Check WebSocket handler for logs
            ws_handler = get_ws_handler()
            if ws_handler:
                logs = ws_handler.get_logs(10)
                for log in logs:
                    await websocket.send_json({
                        "type": "log",
                        "data": log
                    })
            
            # Small delay to prevent busy loop
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error sending update: {e}")
            break


async def receive_messages(websocket: WebSocket):
    """Receive messages from WebSocket client"""
    while True:
        try:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            
        except WebSocketDisconnect:
            raise
        except Exception as e:
            logger.error(f"Error receiving message: {e}")


def broadcast_progress(job_id: str, progress: float, message: str):
    """Broadcast progress update to all connected clients"""
    try:
        progress_queue.put_nowait({
            "job_id": job_id,
            "progress": progress,
            "message": message
        })
    except:
        pass


def broadcast_log(message: str, level: str = "INFO"):
    """Broadcast log message to all connected clients"""
    from datetime import datetime
    try:
        log_queue.put_nowait({
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message
        })
    except:
        pass


async def broadcast_to_all(message: Dict[str, Any]):
    """Broadcast a message to all connected WebSocket clients"""
    disconnected = set()
    
    for websocket in active_connections:
        try:
            await websocket.send_json(message)
        except Exception:
            disconnected.add(websocket)
    
    # Remove disconnected clients
    for ws in disconnected:
        active_connections.discard(ws)
