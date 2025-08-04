# Utilitaires de compression optimisée
# UpscalingByNetwork/server/utils/compression.py

import zipfile
import zlib
import asyncio
import logging
from pathlib import Path
from typing import List, Optional

class BatchCompressor:
    """Gestionnaire de compression pour les lots d'images"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration pour images (pas de compression car souvent déjà optimisées)
        self.compression_level = zipfile.ZIP_STORED  # Pas de compression
        self.compresslevel = 0
    
    async def create_batch_zip(self, input_dir: Path, output_zip: Path) -> bool:
        """Crée un ZIP d'un lot d'images"""
        try:
            # Utilisation d'un thread séparé pour éviter de bloquer
            await asyncio.get_event_loop().run_in_executor(
                None, self._create_zip_sync, input_dir, output_zip
            )
            
            self.logger.debug(f"ZIP créé: {output_zip}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur création ZIP {output_zip}: {e}")
            return False
    
    def _create_zip_sync(self, input_dir: Path, output_zip: Path):
        """Création synchrone du ZIP"""
        with zipfile.ZipFile(output_zip, 'w', self.compression_level) as zf:
            for file_path in input_dir.glob("*.png"):
                if file_path.is_file():
                    # Ajout avec nom relatif
                    arcname = file_path.name
                    zf.write(file_path, arcname)
    
    async def extract_batch_zip(self, zip_path: Path, output_dir: Path) -> bool:
        """Extrait un ZIP de lot"""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            await asyncio.get_event_loop().run_in_executor(
                None, self._extract_zip_sync, zip_path, output_dir
            )
            
            self.logger.debug(f"ZIP extrait: {zip_path} -> {output_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur extraction ZIP {zip_path}: {e}")
            return False
    
    def _extract_zip_sync(self, zip_path: Path, output_dir: Path):
        """Extraction synchrone du ZIP"""
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Vérification de sécurité des noms de fichiers
            for member in zf.namelist():
                if self._is_safe_path(member):
                    zf.extract(member, output_dir)
                else:
                    self.logger.warning(f"Chemin dangereux ignoré: {member}")
    
    def _is_safe_path(self, path: str) -> bool:
        """Vérifie qu'un chemin est sûr (pas de directory traversal)"""
        # Interdiction des chemins absolus et remontées de répertoire
        return not (
            path.startswith('/') or 
            path.startswith('\\') or 
            '..' in path or
            ':' in path
        )
    
    def get_zip_info(self, zip_path: Path) -> Optional[dict]:
        """Retourne les informations d'un ZIP"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                files = zf.namelist()
                total_size = sum(zf.getinfo(name).file_size for name in files)
                compressed_size = sum(zf.getinfo(name).compress_size for name in files)
                
                return {
                    'file_count': len(files),
                    'total_size': total_size,
                    'compressed_size': compressed_size,
                    'compression_ratio': compressed_size / total_size if total_size > 0 else 0,
                    'files': files
                }
        except Exception as e:
            self.logger.error(f"Erreur lecture info ZIP {zip_path}: {e}")
            return None