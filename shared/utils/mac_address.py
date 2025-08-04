# UpscalingByNetwork/shared/utils/mac_address.py

import uuid
import platform
import subprocess
import re
import logging
from typing import Optional, List

def get_primary_mac_address() -> str:
    """
    Récupère l'adresse MAC principale de la machine
    
    Returns:
        Adresse MAC au format standard (XX:XX:XX:XX:XX:XX)
    """
    try:
        # Méthode 1: uuid.getnode() - plus fiable
        mac_int = uuid.getnode()
        mac_hex = f"{mac_int:012x}"
        mac_formatted = ":".join(mac_hex[i:i+2] for i in range(0, 12, 2))
        
        # Vérification que ce n'est pas une MAC factice
        if mac_formatted != "00:00:00:00:00:00" and not mac_formatted.startswith("02:"):
            return mac_formatted.upper()
        
        # Méthode 2: Commandes système spécifiques
        return _get_mac_from_system() or mac_formatted.upper()
        
    except Exception as e:
        logging.error(f"Erreur récupération MAC: {e}")
        # Fallback avec MAC basée sur l'hostname
        return _generate_fallback_mac()

def _get_mac_from_system() -> Optional[str]:
    """Récupère la MAC via les commandes système"""
    try:
        system = platform.system().lower()
        
        if system == "windows":
            return _get_mac_windows()
        elif system == "linux":
            return _get_mac_linux()
        elif system == "darwin":  # macOS
            return _get_mac_macos()
        
        return None
        
    except Exception as e:
        logging.error(f"Erreur MAC système: {e}")
        return None

def _get_mac_windows() -> Optional[str]:
    """Récupère la MAC sur Windows"""
    try:
        # Commande getmac
        result = subprocess.run(
            ["getmac", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line and ',' in line:
                    mac = line.split(',')[0].strip('"')
                    if _is_valid_mac(mac) and not mac.startswith("00-00"):
                        return mac.replace('-', ':').upper()
        
        return None
        
    except Exception:
        return None

def _get_mac_linux() -> Optional[str]:
    """Récupère la MAC sur Linux"""
    try:
        # Lecture de /sys/class/net
        import os
        net_dir = "/sys/class/net"
        
        if os.path.exists(net_dir):
            for interface in os.listdir(net_dir):
                if interface.startswith(('eth', 'enp', 'eno', 'wlan', 'wlp')):
                    mac_file = os.path.join(net_dir, interface, "address")
                    if os.path.exists(mac_file):
                        with open(mac_file, 'r') as f:
                            mac = f.read().strip()
                            if _is_valid_mac(mac) and not mac.startswith("00:00"):
                                return mac.upper()
        
        # Fallback avec ip command
        result = subprocess.run(
            ["ip", "link", "show"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            mac_pattern = r'([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})'
            macs = re.findall(mac_pattern, result.stdout)
            
            for mac in macs:
                if not mac.startswith("00:00") and mac != "ff:ff:ff:ff:ff:ff":
                    return mac.upper()
        
        return None
        
    except Exception:
        return None

def _get_mac_macos() -> Optional[str]:
    """Récupère la MAC sur macOS"""
    try:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Recherche des MAC dans la sortie ifconfig
            mac_pattern = r'ether ([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})'
            macs = re.findall(mac_pattern, result.stdout)
            
            for mac in macs:
                if not mac.startswith("00:00") and mac != "ff:ff:ff:ff:ff:ff":
                    return mac.upper()
        
        return None
        
    except Exception:
        return None

def _is_valid_mac(mac: str) -> bool:
    """Vérifie si une adresse MAC est valide"""
    if not mac:
        return False
    
    # Pattern MAC standard
    mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
    return bool(re.match(mac_pattern, mac))

def _generate_fallback_mac() -> str:
    """Génère une MAC de fallback basée sur l'hostname"""
    try:
        import hashlib
        import socket
        
        hostname = socket.gethostname()
        hash_obj = hashlib.md5(hostname.encode())
        hash_hex = hash_obj.hexdigest()
        
        # Construction d'une MAC à partir du hash
        # Premier octet avec bit local à 1 pour indiquer que c'est local
        mac_parts = [f"02{hash_hex[:2]}"]  # 02 = local, unicast
        mac_parts.extend([hash_hex[i:i+2] for i in range(2, 12, 2)])
        
        return ":".join(mac_parts).upper()
        
    except Exception:
        # Dernière chance: MAC complètement aléatoire
        import random
        mac_parts = ["02"]  # Local unicast
        mac_parts.extend([f"{random.randint(0, 255):02x}" for _ in range(5)])
        return ":".join(mac_parts).upper()

def get_all_mac_addresses() -> List[str]:
    """
    Récupère toutes les adresses MAC disponibles
    
    Returns:
        Liste des adresses MAC détectées
    """
    macs = []
    
    try:
        system = platform.system().lower()
        
        if system == "windows":
            macs = _get_all_macs_windows()
        elif system == "linux":
            macs = _get_all_macs_linux()
        elif system == "darwin":
            macs = _get_all_macs_macos()
        
        # Filtrage des MAC valides
        valid_macs = []
        for mac in macs:
            if (_is_valid_mac(mac) and 
                not mac.startswith("00:00") and 
                mac != "ff:ff:ff:ff:ff:ff"):
                valid_macs.append(mac.upper())
        
        return list(set(valid_macs))  # Suppression des doublons
        
    except Exception as e:
        logging.error(f"Erreur récupération toutes les MAC: {e}")
        return [get_primary_mac_address()]

def _get_all_macs_windows() -> List[str]:
    """Récupère toutes les MAC sur Windows"""
    macs = []
    
    try:
        result = subprocess.run(
            ["getmac", "/fo", "csv", "/nh", "/v"],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line and ',' in line:
                    parts = line.split(',')
                    if len(parts) >= 1:
                        mac = parts[0].strip('"')
                        if mac and mac != "N/A":
                            macs.append(mac.replace('-', ':'))
        
    except Exception:
        pass
    
    return macs

def _get_all_macs_linux() -> List[str]:
    """Récupère toutes les MAC sur Linux"""
    macs = []
    
    try:
        import os
        net_dir = "/sys/class/net"
        
        if os.path.exists(net_dir):
            for interface in os.listdir(net_dir):
                if interface != "lo":  # Ignorer loopback
                    mac_file = os.path.join(net_dir, interface, "address")
                    if os.path.exists(mac_file):
                        try:
                            with open(mac_file, 'r') as f:
                                mac = f.read().strip()
                                if mac:
                                    macs.append(mac)
                        except Exception:
                            continue
    
    except Exception:
        pass
    
    return macs

def _get_all_macs_macos() -> List[str]:
    """Récupère toutes les MAC sur macOS"""
    macs = []
    
    try:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0:
            mac_pattern = r'ether ([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})'
            macs = re.findall(mac_pattern, result.stdout)
    
    except Exception:
        pass
    
    return macs

def normalize_mac_address(mac: str) -> str:
    """
    Normalise une adresse MAC au format standard
    
    Args:
        mac: Adresse MAC à normaliser
        
    Returns:
        Adresse MAC normalisée (XX:XX:XX:XX:XX:XX)
    """
    if not mac:
        return ""
    
    # Suppression des caractères non-hex
    clean_mac = re.sub(r'[^0-9a-fA-F]', '', mac)
    
    if len(clean_mac) != 12:
        return ""
    
    # Formatage avec :
    formatted = ":".join(clean_mac[i:i+2] for i in range(0, 12, 2))
    return formatted.upper()

def is_multicast_mac(mac: str) -> bool:
    """Vérifie si une MAC est multicast"""
    if not _is_valid_mac(mac):
        return False
    
    first_octet = int(mac.split(':')[0], 16)
    return bool(first_octet & 0x01)

def is_local_mac(mac: str) -> bool:
    """Vérifie si une MAC est localement administrée"""
    if not _is_valid_mac(mac):
        return False
    
    first_octet = int(mac.split(':')[0], 16)
    return bool(first_octet & 0x02)