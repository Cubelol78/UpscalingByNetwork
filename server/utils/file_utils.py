import logging
import os
import sys
from pathlib import Path
import hashlib
import socket
import psutil
from typing import Optional, Dict, Any
from datetime import datetime

# utils/file_utils.py
def ensure_dir(directory: Path) -> Path:
    """S'assure qu'un dossier existe"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return directory

def get_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
    """Calcule le hash d'un fichier"""
    hash_func = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()

def get_video_info(video_path: str) -> Optional[Dict[str, Any]]:
    """Obtient les informations basiques d'une vidéo"""
    try:
        import subprocess
        
        # Commande ffprobe pour obtenir les infos
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            
            video_stream = None
            audio_stream = None
            
            # Recherche des streams vidéo et audio
            for stream in info.get('streams', []):
                if stream['codec_type'] == 'video' and not video_stream:
                    video_stream = stream
                elif stream['codec_type'] == 'audio' and not audio_stream:
                    audio_stream = stream
            
            if video_stream:
                # Calcul du framerate
                r_frame_rate = video_stream.get('r_frame_rate', '30/1')
                if '/' in r_frame_rate:
                    num, den = r_frame_rate.split('/')
                    frame_rate = float(num) / float(den)
                else:
                    frame_rate = float(r_frame_rate)
                
                return {
                    'width': int(video_stream.get('width', 0)),
                    'height': int(video_stream.get('height', 0)),
                    'frame_rate': round(frame_rate, 3),
                    'duration': float(info['format'].get('duration', 0)),
                    'has_audio': audio_stream is not None,
                    'video_codec': video_stream.get('codec_name', ''),
                    'audio_codec': audio_stream.get('codec_name', '') if audio_stream else None
                }
        
        return None
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Erreur analyse vidéo: {e}")
        return None

def format_file_size(size_bytes: int) -> str:
    """Formate une taille de fichier en format lisible"""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f}{size_names[i]}"

def format_duration(seconds: int) -> str:
    """Formate une durée en format lisible"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs}s"