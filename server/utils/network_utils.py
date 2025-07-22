import logging
import os
import sys
from pathlib import Path
import hashlib
import socket
import psutil
from typing import Optional, Dict, Any
from datetime import datetime

# utils/network_utils.py
def get_local_ip() -> str:
    """Obtient l'adresse IP locale"""
    try:
        # Connexion vers un serveur externe pour déterminer l'IP locale
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def get_system_info() -> Dict[str, Any]:
    """Obtient les informations système"""
    try:
        return {
            'hostname': socket.gethostname(),
            'platform': sys.platform,
            'cpu_count': psutil.cpu_count(),
            'cpu_freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {},
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'percent': psutil.virtual_memory().percent
            },
            'disk': {
                'total': psutil.disk_usage('/').total,
                'free': psutil.disk_usage('/').free,
                'percent': psutil.disk_usage('/').percent
            }
        }
    except Exception as e:
        logging.getLogger(__name__).error(f"Erreur info système: {e}")
        return {}

def check_port_available(host: str, port: int) -> bool:
    """Vérifie si un port est disponible"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result != 0
    except Exception:
        return False

def get_network_interfaces() -> Dict[str, str]:
    """Obtient les interfaces réseau disponibles"""
    interfaces = {}
    try:
        for interface, addresses in psutil.net_if_addrs().items():
            for addr in addresses:
                if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                    interfaces[interface] = addr.address
                    break
    except Exception as e:
        logging.getLogger(__name__).error(f"Erreur interfaces réseau: {e}")
    
    return interfaces