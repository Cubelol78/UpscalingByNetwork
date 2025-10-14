"""
WebSocket connection manager for the distributed upscaling client
Handles connection, reconnection, and message handling
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable
from enum import Enum

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    from websockets.exceptions import ConnectionClosed, WebSocketException

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketClientProtocol = None


class ConnectionState(Enum):
    """Connection states"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATING = "authenticating"
    READY = "ready"
    ERROR = "error"
    RECONNECTING = "reconnecting"


class ConnectionManager:
    """Manage WebSocket connection to server"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        use_ssl: bool = False,
        auto_reconnect: bool = True,
        reconnect_delay: int = 10,
        max_reconnect_attempts: int = 0,
    ):
        self.logger = logging.getLogger(__name__)

        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError("websockets library not installed")

        # Connection parameters
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts

        # State
        self.state = ConnectionState.DISCONNECTED
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.reconnect_attempts = 0

        # Callbacks
        self.message_handlers: Dict[str, Callable] = {}
        self.event_callbacks: Dict[str, Callable] = {}

        # Statistics
        self.stats = {
            "connect_time": None,
            "last_message_time": None,
            "messages_sent": 0,
            "messages_received": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "reconnections": 0,
        }

        # Tasks
        self.receive_task: Optional[asyncio.Task] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.reconnect_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return (
            self.state in [ConnectionState.CONNECTED, ConnectionState.READY]
            and self.websocket is not None
            and not self.websocket.closed
        )

    @property
    def is_ready(self) -> bool:
        """Check if ready for operations"""
        return self.state == ConnectionState.READY and self.is_connected

    def register_message_handler(self, message_type: str, handler: Callable):
        """Register a message type handler"""
        self.message_handlers[message_type] = handler
        self.logger.debug(f"Registered handler for message type: {message_type}")

    def register_event_callback(self, event_type: str, callback: Callable):
        """Register an event callback"""
        self.event_callbacks[event_type] = callback
        self.logger.debug(f"Registered callback for event: {event_type}")

    async def connect(self) -> bool:
        """
        Connect to server

        Returns:
            True if connected successfully
        """
        if self.is_connected:
            self.logger.warning("Already connected")
            return True

        self.state = ConnectionState.CONNECTING
        self._emit_event("connecting", {})

        try:
            # Build WebSocket URI
            protocol = "wss" if self.use_ssl else "ws"
            uri = f"{protocol}://{self.host}:{self.port}"

            self.logger.info(f"Connecting to {uri}")

            # Connect with timeout
            self.websocket = await asyncio.wait_for(
                websockets.connect(uri, ping_interval=30, ping_timeout=10),
                timeout=30,
            )

            self.state = ConnectionState.CONNECTED
            self.stats["connect_time"] = time.time()
            self.reconnect_attempts = 0

            # Start receive loop
            self.receive_task = asyncio.create_task(self._receive_loop())

            self._emit_event("connected", {"uri": uri})
            self.logger.info(f"Connected to {uri}")

            return True

        except asyncio.TimeoutError:
            self.logger.error("Connection timeout")
            self.state = ConnectionState.ERROR
            self._emit_event("connection_error", {"error": "Timeout"})
            return False

        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            self.state = ConnectionState.ERROR
            self._emit_event("connection_error", {"error": str(e)})
            return False

    async def disconnect(self):
        """Disconnect from server"""
        if not self.websocket:
            return

        self.logger.info("Disconnecting from server")
        self.auto_reconnect = False

        # Cancel tasks
        for task in [self.receive_task, self.heartbeat_task, self.reconnect_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close WebSocket
        if not self.websocket.closed:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")

        self.websocket = None
        self.state = ConnectionState.DISCONNECTED
        self._emit_event("disconnected", {})

        self.logger.info("Disconnected from server")

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send message to server

        Args:
            message: Message dictionary

        Returns:
            True if sent successfully
        """
        if not self.is_connected:
            self.logger.error("Cannot send message: not connected")
            return False

        try:
            message_json = json.dumps(message)
            await self.websocket.send(message_json)

            self.stats["messages_sent"] += 1
            self.stats["bytes_sent"] += len(message_json)

            self.logger.debug(f"Sent message: {message.get('type', 'unknown')}")
            return True

        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False

    async def _receive_loop(self):
        """Message receive loop"""
        try:
            while self.is_connected:
                try:
                    message_raw = await self.websocket.recv()
                    message = json.loads(message_raw)

                    self.stats["messages_received"] += 1
                    self.stats["bytes_received"] += len(message_raw)
                    self.stats["last_message_time"] = time.time()

                    await self._handle_message(message)

                except ConnectionClosed:
                    self.logger.info("Connection closed by server")
                    break

                except json.JSONDecodeError as e:
                    self.logger.error(f"Invalid JSON message: {e}")

                except Exception as e:
                    self.logger.error(f"Error receiving message: {e}")
                    break

        except asyncio.CancelledError:
            pass

        except Exception as e:
            self.logger.error(f"Receive loop error: {e}")

        finally:
            # Trigger reconnection if enabled
            if self.auto_reconnect and self.state != ConnectionState.DISCONNECTED:
                self.reconnect_task = asyncio.create_task(self._reconnect())

    async def _handle_message(self, message: Dict[str, Any]):
        """Handle incoming message"""
        message_type = message.get("type", "unknown")

        self.logger.debug(f"Received message: {message_type}")

        # Find and call handler
        handler = self.message_handlers.get(message_type)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                self.logger.error(f"Error in handler for {message_type}: {e}")
        else:
            self.logger.warning(f"No handler for message type: {message_type}")

    async def _reconnect(self):
        """Attempt to reconnect"""
        if not self.auto_reconnect:
            return

        self.state = ConnectionState.RECONNECTING
        self.stats["reconnections"] += 1

        while self.auto_reconnect:
            self.reconnect_attempts += 1

            # Check max attempts
            if (
                self.max_reconnect_attempts > 0
                and self.reconnect_attempts > self.max_reconnect_attempts
            ):
                self.logger.error("Max reconnection attempts reached")
                self._emit_event("reconnection_failed", {})
                break

            self.logger.info(
                f"Reconnection attempt {self.reconnect_attempts} "
                f"in {self.reconnect_delay}s"
            )

            await asyncio.sleep(self.reconnect_delay)

            if await self.connect():
                self.logger.info("Reconnected successfully")
                self._emit_event("reconnected", {})
                break

    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit event to registered callbacks"""
        if event_type in self.event_callbacks:
            try:
                callback = self.event_callbacks[event_type]
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(data))
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"Error in event callback {event_type}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        stats = self.stats.copy()

        if stats["connect_time"]:
            stats["uptime"] = time.time() - stats["connect_time"]
        else:
            stats["uptime"] = 0

        stats["state"] = self.state.value
        stats["reconnect_attempts"] = self.reconnect_attempts

        return stats

    async def start_heartbeat(self, interval: int = 30):
        """Start heartbeat task"""
        if self.heartbeat_task and not self.heartbeat_task.done():
            return

        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))

    async def _heartbeat_loop(self, interval: int):
        """Heartbeat loop"""
        try:
            while self.is_connected:
                await asyncio.sleep(interval)

                if self.is_connected:
                    heartbeat_message = {
                        "type": "heartbeat",
                        "timestamp": time.time(),
                    }
                    await self.send_message(heartbeat_message)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Heartbeat error: {e}")
