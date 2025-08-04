# UpscalingByNetwork/server/core/__init__.py
"""
Module principal du serveur distribué
"""

from .distributed_server import DistributedServer

__all__ = ['DistributedServer']