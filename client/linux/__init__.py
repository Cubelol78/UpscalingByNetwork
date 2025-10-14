"""
Linux Client for Distributed Upscaling Network
Cross-platform upscaling client with CLI and GUI support
"""

__version__ = "1.0.0"
__author__ = "Upscaling Network Team"
__platform__ = "linux"

from .core.client import DistributedUpscalingClient
from .utils.config import ClientConfig

__all__ = ["DistributedUpscalingClient", "ClientConfig"]
