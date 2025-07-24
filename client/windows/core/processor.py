# client/windows/core/processor.py
"""
Processeur client pour l'upscaling distribué - Version corrigée
Gère la réception, traitement et renvoi des lots
"""

import os
import sys
import tempfile
import zipfile
import subprocess
import asyncio
import logging
import shutil
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import io

# Imports corrigés avec chemins absolus
sys.path.append(str(Path(__file__).parent.parent))

from security.client_security import ClientSecurity
from utils.config import config, ClientConfig
from utils.system_info import SystemInfo

class ClientProcessor:
    """
    Processeur client pour l'upscaling distribué
    Gère la réception, traitement et renvoi des lots
    """
    
    def __init__(self, client_instance):
        self.client = client_instance
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.security = ClientSecurity()
        self.system_info = SystemInfo()
        
        # État du processeur
        self.is_processing = False
        self.current_batch_id = None
        self.processing_start_time = None
        
        # Dossiers de travail
        self.work_dir = self.config.get_work_directory()
        self.temp_dir = self.work_dir / "temp"
        self.input_dir = self.work_dir / "input"
        self.output_dir = self.work_dir / "output"
        
        # Création des dossiers
        for directory in [self.temp_dir, self.input_dir, self.output_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Chemin vers Real-ESRGAN
        self.realesrgan_path = self._find_realesrgan_executable()
        
        # Configuration Real-ESRGAN
        self.realesrgan_config = {
            'model': self.config.get("processing.realesrgan_model", "RealESRGAN_x4plus"),
            'scale': 4,
            'tile_size': self.config.get("processing.tile_size", 256),
            'use_gpu': self.config.get("processing.use_gpu", True)
        }
        
        # Statistiques
        self.stats = {
            'batches_processed': 0,
            'total_frames_processed': 0,
            'total_processing_time': 0,
            'average_time_per_frame': 0,
            'errors_count': 0,
            'last_error': None,
            'data_received_mb': 0,
            'data_sent_mb': 0
        }
        
        self.logger.info(f"Processeur client initialisé - Real-ESRGAN: {self.realesrgan_path}")
    
    def _find_realesrgan_executable(self) -> Optional[str]:
        """Trouve l'exécutable Real-ESRGAN selon la plateforme"""
        if sys.platform == "win32":
            executable_name = "realesrgan-ncnn-vulkan.exe"
        else:
            executable_name = "realesrgan-ncnn-vulkan"
        
        # 1. Recherche dans le dossier des dépendances
        client_dir = Path(__file__).parent.parent.parent
        dependencies_dir = client_dir / "dependencies"
        executable_path = dependencies_dir / executable_name
        
        if executable_path.exists():
            self.logger.info(f"Real-ESRGAN trouvé: {executable_path}")
            return str(executable_path)
        
        # 2. Recherche dans la configuration
        config_path = self.config.get("paths.realesrgan_executable")
        if config_path and Path(config_path).exists():
            self.logger.info(f"Real-ESRGAN trouvé via config: {config_path}")
            return config_path
        
        # 3. Recherche dans le PATH système
        system_path = shutil.which(executable_name)
        if system_path:
            self.logger.info(f"Real-ESRGAN trouvé dans PATH: {system_path}")
            return system_path
        
        # 4. Recherche dans des emplacements standards
        standard_locations = [
            Path.cwd() / executable_name,
            Path.cwd() / "bin" / executable_name,
            Path.cwd() / "tools" / executable_name,
            Path.home() / "tools" / executable_name
        ]
        
        for location in standard_locations:
            if location.exists():
                self.logger.info(f"Real-ESRGAN trouvé: {location}")
                return str(location)
        
        self.logger.warning("Real-ESRGAN non trouvé - fonctionnalité d'upscaling indisponible")
        return None
    
    async def process_batch(self, batch_data: bytes, batch_id: str, batch_config: Dict) -> Optional[bytes]:
        """
        Traite un lot d'images
        
        Args:
            batch_data: Données du lot chiffrées
            batch_id: Identifiant du lot
            batch_config: Configuration de traitement
            
        Returns:
            Données du lot traité chiffrées ou None en cas d'erreur
        """
        if self.is_processing:
            self.logger.warning(f"Tentative de traitement du lot {batch_id} alors qu'un traitement est en cours")
            return None
        
        self.is_processing = True
        self.current_batch_id = batch_id
        self.processing_start_time = time.time()
        
        try:
            self.logger.info(f"Début traitement lot {batch_id}")
            
            # 1. Déchiffrement et décompression des données
            decrypted_data = self.security.decrypt_data(batch_data)
            if decrypted_data is None:
                raise Exception("Échec déchiffrement des données")
            
            self.stats['data_received_mb'] += len(batch_data) / (1024 * 1024)
            
            # 2. Extraction du lot dans le dossier de travail
            batch_input_dir = self.input_dir / batch_id
            batch_output_dir = self.output_dir / batch_id
            
            # Nettoyage des dossiers précédents
            if batch_input_dir.exists():
                shutil.rmtree(batch_input_dir)
            if batch_output_dir.exists():
                shutil.rmtree(batch_output_dir)
            
            batch_input_dir.mkdir(parents=True)
            batch_output_dir.mkdir(parents=True)
            
            # 3. Décompression du ZIP
            zip_path = self.temp_dir / f"{batch_id}.zip"
            with open(zip_path, 'wb') as f:
                f.write(decrypted_data)
            
            extracted_files = self._extract_batch_zip(zip_path, batch_input_dir)
            if not extracted_files:
                raise Exception("Aucun fichier extrait du lot")
            
            self.logger.info(f"Lot {batch_id}: {len(extracted_files)} images extraites")
            
            # 4. Traitement avec Real-ESRGAN
            processed_files = await self._process_images_with_realesrgan(
                batch_input_dir, batch_output_dir, batch_config
            )
            
            if not processed_files:
                raise Exception("Aucune image traitée avec succès")
            
            self.logger.info(f"Lot {batch_id}: {len(processed_files)} images traitées")
            
            # 5. Vérification de l'intégrité (même nombre de fichiers)
            if len(processed_files) != len(extracted_files):
                self.logger.warning(f"Lot {batch_id}: {len(processed_files)} traitées sur {len(extracted_files)} extraites")
            
            # 6. Compression du résultat
            result_zip_path = self.temp_dir / f"{batch_id}_result.zip"
            self._create_result_zip(batch_output_dir, result_zip_path)
            
            # 7. Chiffrement des données de retour
            with open(result_zip_path, 'rb') as f:
                result_data = f.read()
            
            encrypted_result = self.security.encrypt_data(result_data)
            if encrypted_result is None:
                raise Exception("Échec chiffrement des données de retour")
            
            self.stats['data_sent_mb'] += len(encrypted_result) / (1024 * 1024)
            
            # 8. Nettoyage
            self._cleanup_batch_files(batch_id, zip_path, result_zip_path, batch_input_dir, batch_output_dir)
            
            # 9. Mise à jour des statistiques
            processing_time = time.time() - self.processing_start_time
            self.stats['batches_processed'] += 1
            self.stats['total_frames_processed'] += len(processed_files)
            self.stats['total_processing_time'] += processing_time
            self.stats['average_time_per_frame'] = (
                self.stats['total_processing_time'] / max(1, self.stats['total_frames_processed'])
            )
            
            self.logger.info(f"Lot {batch_id} traité avec succès en {processing_time:.1f}s")
            return encrypted_result
            
        except Exception as e:
            self.logger.error(f"Erreur traitement lot {batch_id}: {e}")
            self.stats['errors_count'] += 1
            self.stats['last_error'] = str(e)
            
            # Nettoyage en cas d'erreur
            try:
                self._cleanup_batch_files(batch_id)
            except:
                pass
            
            return None
            
        finally:
            self.is_processing = False
            self.current_batch_id = None
            self.processing_start_time = None
    
    def _extract_batch_zip(self, zip_path: Path, extract_dir: Path) -> List[str]:
        """Extrait un fichier ZIP de lot"""
        extracted_files = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                # Vérification de sécurité des noms de fichiers
                for name in zip_file.namelist():
                    if os.path.isabs(name) or ".." in name:
                        raise Exception(f"Nom de fichier dangereux détecté: {name}")
                
                # Extraction
                zip_file.extractall(extract_dir)
                extracted_files = zip_file.namelist()
            
            # Filtrage des fichiers images
            image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
            extracted_files = [
                f for f in extracted_files 
                if Path(f).suffix.lower() in image_extensions
            ]
            
            return extracted_files
            
        except Exception as e:
            self.logger.error(f"Erreur extraction ZIP {zip_path}: {e}")
            return []
    
    async def _process_images_with_realesrgan(self, input_dir: Path, output_dir: Path, 
                                           batch_config: Dict) -> List[str]:
        """Traite les images avec Real-ESRGAN"""
        if not self.realesrgan_path:
            raise Exception("Real-ESRGAN non disponible")
        
        # Configuration du traitement
        config = self.realesrgan_config.copy()
        config.update(batch_config.get('realesrgan', {}))
        
        # Construction de la commande
        cmd = [
            self.realesrgan_path,
            '-i', str(input_dir),
            '-o', str(output_dir),
            '-n', config.get('model', 'RealESRGAN_x4plus'),
            '-s', str(config.get('scale', 4)),
            '-t', str(config.get('tile_size', 256)),
            '-f', 'png'
        ]
        
        # Options supplémentaires
        if not config.get('use_gpu', True):
            cmd.extend(['-g', '-1'])  # CPU seulement
        
        if config.get('tta_mode', False):
            cmd.append('-x')  # Mode TTA (Test-Time Augmentation)
        
        try:
            # Exécution de Real-ESRGAN
            self.logger.info(f"Exécution Real-ESRGAN: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise Exception(f"Real-ESRGAN a échoué (code {process.returncode}): {error_msg}")
            
            # Vérification des fichiers de sortie
            output_files = []
            for file_path in output_dir.glob('*.png'):
                if file_path.is_file() and file_path.stat().st_size > 0:
                    output_files.append(file_path.name)
            
            if not output_files:
                raise Exception("Aucun fichier de sortie généré par Real-ESRGAN")
            
            self.logger.info(f"Real-ESRGAN terminé - {len(output_files)} fichiers générés")
            return output_files
            
        except Exception as e:
            self.logger.error(f"Erreur exécution Real-ESRGAN: {e}")
            raise
    
    def _create_result_zip(self, output_dir: Path, zip_path: Path):
        """Crée un fichier ZIP avec les résultats"""
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zip_file:  # ZIP_STORED = pas de compression
                for file_path in output_dir.glob('*'):
                    if file_path.is_file():
                        zip_file.write(file_path, file_path.name)
            
            self.logger.info(f"ZIP résultat créé: {zip_path}")
            
        except Exception as e:
            self.logger.error(f"Erreur création ZIP résultat: {e}")
            raise
    
    def _cleanup_batch_files(self, batch_id: str, *additional_paths):
        """Nettoie les fichiers temporaires d'un lot"""
        try:
            # Dossiers du lot
            batch_input_dir = self.input_dir / batch_id
            batch_output_dir = self.output_dir / batch_id
            
            for directory in [batch_input_dir, batch_output_dir]:
                if directory.exists():
                    shutil.rmtree(directory)
            
            # Fichiers temporaires supplémentaires
            for path in additional_paths:
                if path and Path(path).exists():
                    Path(path).unlink()
            
            self.logger.debug(f"Nettoyage lot {batch_id} terminé")
            
        except Exception as e:
            self.logger.error(f"Erreur nettoyage lot {batch_id}: {e}")
    
    def test_realesrgan(self) -> Dict[str, any]:
        """
        Teste la disponibilité et le fonctionnement de Real-ESRGAN
        
        Returns:
            Dictionnaire avec les résultats du test
        """
        test_result = {
            'available': False,
            'executable_path': self.realesrgan_path,
            'version': None,
            'models_available': [],
            'gpu_support': False,
            'test_success': False,
            'error': None
        }
        
        if not self.realesrgan_path:
            test_result['error'] = "Exécutable Real-ESRGAN non trouvé"
            return test_result
        
        try:
            # Test de base - version
            result = subprocess.run([self.realesrgan_path, '-h'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                test_result['available'] = True
                
                # Extraction de la version si possible
                output = result.stdout + result.stderr
                for line in output.split('\n'):
                    if 'Real-ESRGAN' in line and ('version' in line.lower() or 'v' in line):
                        test_result['version'] = line.strip()
                        break
            
            # Test des modèles disponibles
            models_dir = Path(self.realesrgan_path).parent / "models"
            if models_dir.exists():
                model_files = list(models_dir.glob("*.bin"))
                test_result['models_available'] = [f.stem for f in model_files]
            
            # Test GPU (très basique)
            if self.system_info.is_gpu_available():
                test_result['gpu_support'] = True
            
            test_result['test_success'] = True
            self.logger.info("Test Real-ESRGAN réussi")
            
        except subprocess.TimeoutExpired:
            test_result['error'] = "Timeout lors du test Real-ESRGAN"
        except Exception as e:
            test_result['error'] = f"Erreur test Real-ESRGAN: {e}"
        
        return test_result
    
    def get_processing_capabilities(self) -> Dict[str, any]:
        """
        Retourne les capacités de traitement du client
        
        Returns:
            Dictionnaire avec les capacités
        """
        system_info = self.system_info.get_system_info()
        realesrgan_test = self.test_realesrgan()
        
        return {
            'system_info': {
                'platform': system_info['basic']['platform'],
                'cpu_cores': system_info['hardware']['cpu'].get('logical_cores', 1),
                'ram_gb': system_info['hardware']['memory'].get('total_ram_gb', 0),
                'gpu_available': self.system_info.is_gpu_available(),
                'vulkan_support': system_info['vulkan']['supported']
            },
            'realesrgan': {
                'available': realesrgan_test['available'],
                'path': realesrgan_test['executable_path'],
                'version': realesrgan_test['version'],
                'models': realesrgan_test['models_available'],
                'gpu_support': realesrgan_test['gpu_support']
            },
            'performance_score': self.system_info.get_performance_score(),
            'recommended_config': self._get_recommended_config(),
            'max_concurrent_batches': self.config.get("processing.max_concurrent_batches", 1)
        }
    
    def _get_recommended_config(self) -> Dict[str, any]:
        """
        Génère une configuration recommandée basée sur le matériel
        
        Returns:
            Configuration recommandée
        """
        performance_score = self.system_info.get_performance_score()
        ram_gb = self.system_info.get_memory_gb()
        gpu_available = self.system_info.is_gpu_available()
        
        config = {
            'tile_size': 256,
            'use_gpu': gpu_available,
            'tta_mode': False,
            'model': 'RealESRGAN_x4plus'
        }
        
        # Ajustement basé sur la performance
        if performance_score >= 80:
            # Configuration haute performance
            config['tile_size'] = 512
            config['tta_mode'] = True
        elif performance_score >= 60:
            # Configuration moyenne
            config['tile_size'] = 384
        elif performance_score < 40:
            # Configuration conservatrice
            config['tile_size'] = 128
            config['use_gpu'] = False  # Forcer CPU si performance très faible
        
        # Ajustement basé sur la RAM
        if ram_gb < 4:
            config['tile_size'] = min(config['tile_size'], 128)
            config['tta_mode'] = False
        elif ram_gb >= 16:
            config['tile_size'] = max(config['tile_size'], 384)
        
        return config
    
    def get_stats(self) -> Dict[str, any]:
        """
        Retourne les statistiques du processeur
        
        Returns:
            Dictionnaire avec les statistiques
        """
        return {
            'processing_state': {
                'is_processing': self.is_processing,
                'current_batch_id': self.current_batch_id,
                'processing_duration': (
                    time.time() - self.processing_start_time 
                    if self.processing_start_time else 0
                )
            },
            'performance_stats': self.stats.copy(),
            'system_resources': {
                'cpu_percent': self.system_info._get_performance_info().get('cpu_percent_total', 0),
                'memory_percent': self.system_info._get_performance_info().get('memory_percent', 0),
                'disk_percent': self.system_info._get_performance_info().get('disk_percent', 0)
            },
            'work_directories': {
                'work_dir': str(self.work_dir),
                'temp_dir': str(self.temp_dir),
                'input_dir': str(self.input_dir),
                'output_dir': str(self.output_dir)
            }
        }
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """
        Nettoie les anciens fichiers temporaires
        
        Args:
            max_age_hours: Âge maximum des fichiers en heures
        """
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            cleaned_count = 0
            
            # Nettoyage des dossiers temporaires
            for directory in [self.temp_dir, self.input_dir, self.output_dir]:
                if not directory.exists():
                    continue
                
                for item in directory.iterdir():
                    try:
                        # Vérification de l'âge
                        if current_time - item.stat().st_mtime > max_age_seconds:
                            if item.is_file():
                                item.unlink()
                                cleaned_count += 1
                            elif item.is_dir():
                                shutil.rmtree(item)
                                cleaned_count += 1
                    except Exception as e:
                        self.logger.warning(f"Impossible de supprimer {item}: {e}")
            
            if cleaned_count > 0:
                self.logger.info(f"Nettoyage terminé: {cleaned_count} éléments supprimés")
            
        except Exception as e:
            self.logger.error(f"Erreur nettoyage fichiers anciens: {e}")
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.stats = {
            'batches_processed': 0,
            'total_frames_processed': 0,
            'total_processing_time': 0,
            'average_time_per_frame': 0,
            'errors_count': 0,
            'last_error': None,
            'data_received_mb': 0,
            'data_sent_mb': 0
        }
        self.logger.info("Statistiques remises à zéro")
    
    def validate_configuration(self) -> Dict[str, any]:
        """
        Valide la configuration du processeur
        
        Returns:
            Résultat de la validation
        """
        validation = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Validation Real-ESRGAN
        if not self.realesrgan_path:
            validation['errors'].append("Exécutable Real-ESRGAN non trouvé")
            validation['valid'] = False
        elif not Path(self.realesrgan_path).exists():
            validation['errors'].append(f"Fichier Real-ESRGAN inexistant: {self.realesrgan_path}")
            validation['valid'] = False
        
        # Validation des dossiers
        for name, directory in [
            ('work', self.work_dir),
            ('temp', self.temp_dir),
            ('input', self.input_dir),
            ('output', self.output_dir)
        ]:
            if not directory.exists():
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    validation['warnings'].append(f"Dossier {name} créé: {directory}")
                except Exception as e:
                    validation['errors'].append(f"Impossible de créer le dossier {name}: {e}")
                    validation['valid'] = False
        
        # Validation de la sécurité
        if not self.security.is_ready():
            validation['errors'].append("Système de sécurité non initialisé")
            validation['valid'] = False
        
        # Validation de la configuration
        if not self.config.validate_config():
            validation['warnings'].append("Configuration client incomplète")
        
        return validation