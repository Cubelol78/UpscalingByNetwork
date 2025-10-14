"""
Main distributed upscaling client
Cross-platform client for Linux, Windows, and macOS
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional, Callable
from pathlib import Path

from .connection import ConnectionManager, ConnectionState
from .processor import ClientProcessor
from .batch_processor import BatchProcessor
from .security import ClientSecurity
from ..utils.config import config
from ..utils.system_info import SystemInfo
from ..utils.realesrgan_handler import RealESRGANHandler


class DistributedUpscalingClient:
    """Main client for distributed upscaling"""

    def __init__(self, config_path: Optional[Path] = None):
        self.logger = logging.getLogger(__name__)

        # Configuration
        if config_path:
            from ..utils.config import ClientConfig

            self.config = ClientConfig(config_path)
        else:
            self.config = config

        # System info
        self.system_info = SystemInfo()

        # Security
        self.security = ClientSecurity()

        # Real-ESRGAN
        try:
            realesrgan_path = self.config.get("paths.realesrgan_executable")
            models_dir = self.config.get("paths.models_directory")
            self.realesrgan = RealESRGANHandler(
                Path(realesrgan_path) if realesrgan_path else None,
                Path(models_dir) if models_dir else None,
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Real-ESRGAN: {e}")
            raise

        # Processor
        self.processor = ClientProcessor(
            self, self.realesrgan, self.security, self.config
        )

        # Batch processor
        max_concurrent = self.config.get("processing.max_batch_size", 1)
        self.batch_processor = BatchProcessor(self.processor, max_concurrent)

        # Connection
        self.connection = ConnectionManager(
            host=self.config.get("server.host"),
            port=self.config.get("server.port"),
            use_ssl=self.config.get("server.use_ssl"),
            auto_reconnect=True,
            reconnect_delay=self.config.get("server.reconnect_delay"),
            max_reconnect_attempts=self.config.get("server.max_reconnection_attempts"),
        )

        # Register message handlers
        self._register_handlers()

        # Client identification
        self.client_id = str(uuid.uuid4())
        self.mac_address = self.system_info.get_mac_address()

        self.logger.info(f"Client initialized - ID: {self.client_id}")

    def _register_handlers(self):
        """Register message handlers"""
        handlers = {
            "server_hello": self._handle_server_hello,
            "batch_assignment": self._handle_batch_assignment,
            "batch_request": self._handle_batch_request,
            "configuration_update": self._handle_configuration_update,
            "ping": self._handle_ping,
            "disconnect": self._handle_disconnect,
            "error": self._handle_error,
        }

        for msg_type, handler in handlers.items():
            self.connection.register_message_handler(msg_type, handler)

    async def connect(
        self, host: Optional[str] = None, port: Optional[int] = None
    ) -> bool:
        """
        Connect to server

        Args:
            host: Server host (uses config if None)
            port: Server port (uses config if None)

        Returns:
            True if connected successfully
        """
        if host:
            self.connection.host = host
        if port:
            self.connection.port = port

        # Connect
        if not await self.connection.connect():
            return False

        # Start heartbeat
        heartbeat_interval = self.config.get("client.heartbeat_interval")
        await self.connection.start_heartbeat(heartbeat_interval)

        # Authenticate
        if not await self._authenticate():
            await self.disconnect()
            return False

        self.logger.info("Client ready")
        return True

    async def disconnect(self):
        """Disconnect from server"""
        await self.connection.disconnect()

    async def _authenticate(self) -> bool:
        """Authenticate with server"""
        try:
            self.connection.state = ConnectionState.AUTHENTICATING

            # Collect system info
            sys_info = self.system_info.get_system_info()

            # Build hello message
            hello_message = {
                "type": "client_hello",
                "client_id": self.client_id,
                "mac_address": self.mac_address,
                "public_key": self.security.get_public_key_pem(),
                "system_info": {
                    "platform": sys_info["basic"]["platform"],
                    "hostname": sys_info["basic"]["hostname"],
                    "cpu_cores": sys_info["hardware"]["cpu"]["logical_cores"],
                    "ram_gb": sys_info["hardware"]["memory"]["total_ram_gb"],
                    "gpu_available": self.system_info.is_gpu_available(),
                    "performance_score": self.system_info.get_performance_score(),
                },
                "capabilities": self.processor.get_capabilities(),
                "version": "1.0.0",
            }

            # Send hello
            await self.connection.send_message(hello_message)

            self.logger.info("Authentication initiated")
            return True

        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            return False

    async def _handle_server_hello(self, message: Dict[str, Any]):
        """Handle server hello response"""
        try:
            status = message.get("status")

            if status != "accepted":
                reason = message.get("message", "Unknown")
                self.logger.error(f"Authentication rejected: {reason}")
                return

            # Set server public key
            server_public_key = message.get("server_public_key")
            if server_public_key:
                self.security.set_server_public_key(server_public_key)

            # Decrypt session key
            encrypted_session_key = message.get("session_key")
            if encrypted_session_key:
                import base64

                encrypted_key_bytes = base64.b64decode(encrypted_session_key)
                if not self.security.decrypt_session_key(encrypted_key_bytes):
                    self.logger.error("Failed to decrypt session key")
                    return

            self.connection.state = ConnectionState.READY
            self.logger.info("Authentication successful")

        except Exception as e:
            self.logger.error(f"Error handling server hello: {e}")

    async def _handle_batch_assignment(self, message: Dict[str, Any]):
        """Handle batch assignment"""
        try:
            batch_id = message.get("batch_id")
            batch_data = message.get("batch_data")
            batch_config = message.get("batch_config", {})

            if not batch_id or not batch_data:
                self.logger.error("Invalid batch assignment")
                return

            self.logger.info(f"Received batch: {batch_id}")

            # Decode data
            import base64

            encrypted_data = base64.b64decode(batch_data)

            # Process batch
            result = await self.processor.process_batch(
                encrypted_data, batch_id, batch_config
            )

            # Send result
            if result:
                result_b64 = base64.b64encode(result).decode("utf-8")

                response = {
                    "type": "batch_result",
                    "batch_id": batch_id,
                    "status": "completed",
                    "result_data": result_b64,
                }
            else:
                response = {
                    "type": "batch_result",
                    "batch_id": batch_id,
                    "status": "failed",
                    "error_message": self.processor.stats.get(
                        "last_error", "Unknown error"
                    ),
                }

            await self.connection.send_message(response)

        except Exception as e:
            self.logger.error(f"Error handling batch assignment: {e}")

    async def _handle_batch_request(self, message: Dict[str, Any]):
        """Handle batch availability request"""
        try:
            batch_id = message.get("batch_id")

            available = (
                self.connection.is_ready
                and not self.processor.is_processing
                and self.security.is_ready()
            )

            response = {
                "type": "batch_availability",
                "batch_id": batch_id,
                "available": available,
                "client_stats": {
                    "performance_score": self.system_info.get_performance_score(),
                    "batches_completed": self.processor.stats["batches_processed"],
                    "current_load": {
                        "cpu_percent": self.system_info.get_cpu_usage(),
                        "memory_percent": self.system_info.get_memory_usage(),
                    },
                },
            }

            await self.connection.send_message(response)

        except Exception as e:
            self.logger.error(f"Error handling batch request: {e}")

    async def _handle_configuration_update(self, message: Dict[str, Any]):
        """Handle configuration update"""
        try:
            new_config = message.get("configuration", {})

            for key, value in new_config.items():
                self.config.set(key, value, save=False)

            self.config.save_config()
            self.logger.info("Configuration updated by server")

        except Exception as e:
            self.logger.error(f"Error updating configuration: {e}")

    async def _handle_ping(self, message: Dict[str, Any]):
        """Handle ping from server"""
        pong = {
            "type": "pong",
            "timestamp": message.get("timestamp", time.time()),
            "client_stats": self.get_status(),
        }
        await self.connection.send_message(pong)

    async def _handle_disconnect(self, message: Dict[str, Any]):
        """Handle disconnect request"""
        reason = message.get("reason", "Server request")
        self.logger.info(f"Disconnecting: {reason}")
        await self.disconnect()

    async def _handle_error(self, message: Dict[str, Any]):
        """Handle error message"""
        error_msg = message.get("message", "Unknown error")
        error_code = message.get("code", "UNKNOWN")
        self.logger.error(f"Server error [{error_code}]: {error_msg}")

    def get_status(self) -> Dict[str, Any]:
        """Get client status"""
        return {
            "client_id": self.client_id,
            "mac_address": self.mac_address,
            "connection_state": self.connection.state.value,
            "is_processing": self.processor.is_processing,
            "performance_score": self.system_info.get_performance_score(),
            "system_load": {
                "cpu_percent": self.system_info.get_cpu_usage(),
                "memory_percent": self.system_info.get_memory_usage(),
            },
        }

    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed status"""
        return {
            "client_info": {
                "client_id": self.client_id,
                "mac_address": self.mac_address,
                "version": "1.0.0",
            },
            "connection": self.connection.get_stats(),
            "system": self.system_info.get_system_info(),
            "processor": self.processor.get_stats(),
            "security": {"session_established": self.security.is_ready()},
        }

    async def cleanup(self):
        """Cleanup client resources"""
        try:
            await self.disconnect()
            self.processor.cleanup_old_files()
            self.config.save_config()
            self.logger.info("Client cleanup complete")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self.connection.is_connected

    @property
    def is_ready(self) -> bool:
        """Check if ready"""
        return self.connection.is_ready and self.security.is_ready()
