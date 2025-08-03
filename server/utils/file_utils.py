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

def format_file_size(size_bytes: int) -> str:
    """Formate une taille de fichier en format lisible"""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1
    
    return f"{size:.1f}{size_names[i]}"

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

def format_file_size_gb(size_gb: float) -> str:
    """Formate une taille en GB de manière adaptative"""
    if size_gb < 1:
        return f"{size_gb * 1024:.0f}MB"
    elif size_gb < 1024:
        return f"{size_gb:.1f}GB"
    else:
        return f"{size_gb / 1024:.1f}TB"

def estimate_video_processing_space(video_path: str) -> dict:
    """Estime l'espace requis pour traiter une vidéo (version améliorée)"""
    try:
        import subprocess
        import json
        
        # Obtenir les infos détaillées de la vidéo
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            info = json.loads(result.stdout)
            
            # Extraire les informations vidéo
            video_stream = None
            for stream in info.get('streams', []):
                if stream['codec_type'] == 'video':
                    video_stream = stream
                    break
            
            if video_stream:
                # Calculs détaillés
                width = int(video_stream.get('width', 1920))
                height = int(video_stream.get('height', 1080))
                duration = float(info['format'].get('duration', 0))
                
                # Calcul du framerate
                r_frame_rate = video_stream.get('r_frame_rate', '30/1')
                if '/' in r_frame_rate:
                    num, den = r_frame_rate.split('/')
                    fps = float(num) / float(den) if float(den) != 0 else 30
                else:
                    fps = float(r_frame_rate)
                
                # Nombre total de frames
                total_frames = int(duration * fps)
                
                # Estimation de l'espace par frame (PNG non compressé)
                # Formule : largeur × hauteur × 3 octets (RGB) + overhead PNG
                original_frame_size = width * height * 3 * 1.2  # +20% pour l'overhead PNG
                upscaled_frame_size = (width * 4) * (height * 4) * 3 * 1.2  # x4 en résolution
                
                # Calculs d'espace en GB
                original_frames_gb = (total_frames * original_frame_size) / (1024**3)
                upscaled_frames_gb = (total_frames * upscaled_frame_size) / (1024**3)
                
                # Fichier vidéo original
                video_size_gb = Path(video_path).stat().st_size / (1024**3)
                
                # Estimations pour audio et sortie
                audio_gb = video_size_gb * 0.1  # ~10% du fichier original
                output_gb = video_size_gb * 2   # Estimation pour la sortie upscalée
                temp_files_gb = video_size_gb * 0.5  # Fichiers temporaires divers
                
                total_required = original_frames_gb + upscaled_frames_gb + audio_gb + output_gb + temp_files_gb
                
                return {
                    'video_info': {
                        'width': width,
                        'height': height,
                        'duration': duration,
                        'fps': fps,
                        'total_frames': total_frames
                    },
                    'space_breakdown': {
                        'original_video_gb': video_size_gb,
                        'original_frames_gb': original_frames_gb,
                        'upscaled_frames_gb': upscaled_frames_gb,
                        'audio_gb': audio_gb,
                        'output_gb': output_gb,
                        'temp_files_gb': temp_files_gb,
                        'total_required_gb': total_required
                    },
                    'formatted_sizes': {
                        'original_frames': format_file_size_gb(original_frames_gb),
                        'upscaled_frames': format_file_size_gb(upscaled_frames_gb),
                        'total_required': format_file_size_gb(total_required)
                    }
                }
        
        # Fallback si ffprobe échoue
        video_size_gb = Path(video_path).stat().st_size / (1024**3)
        estimated_total = video_size_gb * 100  # Estimation conservative
        
        return {
            'space_breakdown': {
                'total_required_gb': estimated_total
            },
            'error': 'Analyse détaillée impossible, estimation conservative utilisée'
        }
        
    except Exception as e:
        return {
            'error': f"Erreur analyse vidéo: {str(e)}",
            'space_breakdown': {'total_required_gb': 0}
        }