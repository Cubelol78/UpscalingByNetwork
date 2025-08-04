# UpscalingByNetwork/client/windows/core/__init__.py
"""
Module principal du client distribué
"""

try:
    from .distributed_client import DistributedClient
    CLIENT_AVAILABLE = True
except ImportError:
    DistributedClient = None
    CLIENT_AVAILABLE = False

__all__ = ['DistributedClient', 'CLIENT_AVAILABLE']