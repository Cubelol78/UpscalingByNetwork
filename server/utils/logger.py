import logging
import os
import sys
from pathlib import Path
import hashlib
import socket
import psutil
from typing import Optional, Dict, Any
from datetime import datetime

# utils/logger.py
class ColoredFormatter(logging.Formatter):
    """Formateur de logs avec couleurs"""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Vert
        'WARNING': '\033[33m',   # Jaune  
        'ERROR': '\033[31m',     # Rouge
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset_color = self.COLORS['RESET']
        
        # Format: [TIMESTAMP] LEVEL - MODULE: MESSAGE
        formatter = logging.Formatter(
            f'{log_color}[%(asctime)s] %(levelname)-8s{reset_color} - %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        return formatter.format(record)

def setup_logger() -> logging.Logger:
    """Configure le système de logging"""
    from config.settings import LOGS_DIR
    
    # Configuration du logger racine
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Suppression des handlers existants
    logger.handlers.clear()
    
    # Handler console avec couleurs
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)
    
    # Handler fichier
    log_file = LOGS_DIR / f"server_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s - %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Réduction du niveau de logging pour certains modules
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Récupère un logger nommé"""
    return logging.getLogger(name)