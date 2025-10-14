"""
Core client modules for distributed upscaling
"""

from .client import DistributedUpscalingClient, ConnectionState
from .processor import ClientProcessor
from .connection import ConnectionManager
from .batch_processor import BatchProcessor

__all__ = [
    "DistributedUpscalingClient",
    "ConnectionState",
    "ClientProcessor",
    "ConnectionManager",
    "BatchProcessor",
]
