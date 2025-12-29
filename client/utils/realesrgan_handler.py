"""
Gestionnaire Real-ESRGAN pour l'upscaling d'images (côté client)
Utilise les exécutables portables fournis
Supporte les options de performance: tile-size, GPU selection, threads, TTA
"""

import os
import subprocess
import platform
from typing import Optional, List, Dict
from pathlib import Path

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import ProcessingConfig


class RealESRGANHandler:
    """Gestionnaire Real-ESRGAN pour upscaling avec options de performance"""

    def __init__(self, ProjectRoot: Optional[str] = None, PerformanceConfig: Optional[Dict] = None):
        """
        Initialise le gestionnaire Real-ESRGAN

        Args:
            ProjectRoot: Racine du projet (détecté auto si None)
            PerformanceConfig: Configuration de performance (tile_size, gpu_ids, threads, tta_mode)
        """
        self.Logger = GetModuleLogger("RealESRGANHandler")
        self.ProjectRoot = ProjectRoot or self._DetectProjectRoot()
        self.ExecutablePath = None
        self.ModelsPath = None
        self.PerformanceConfig = PerformanceConfig or {}

        # Détecte l'exécutable approprié
        self._DetectExecutable()

    def _DetectProjectRoot(self) -> str:
        """
        Détecte la racine du projet

        Returns:
            Chemin vers la racine du projet
        """
        # Remonte jusqu'à trouver le dossier contenant les executables Real-ESRGAN
        CurrentPath = Path(__file__).resolve()

        # Remonte de client/utils vers la racine
        ProjectRoot = CurrentPath.parent.parent.parent

        self.Logger.debug(f"Racine du projet détectée: {ProjectRoot}")
        return str(ProjectRoot)

    def _DetectExecutable(self):
        """Détecte l'exécutable Real-ESRGAN selon l'OS"""
        try:
            System = platform.system()

            if System == "Linux":
                ExecDir = os.path.join(self.ProjectRoot, "realesrgan-ncnn-vulkan-20220424-ubuntu")
                ExecName = "realesrgan-ncnn-vulkan"
                self.ExecutablePath = os.path.join(ExecDir, ExecName)
                self.ModelsPath = os.path.join(ExecDir, "models")

            elif System == "Windows":
                ExecDir = os.path.join(self.ProjectRoot, "realesrgan-ncnn-vulkan-20220424-windows")
                ExecName = "realesrgan-ncnn-vulkan.exe"
                self.ExecutablePath = os.path.join(ExecDir, ExecName)
                self.ModelsPath = os.path.join(ExecDir, "models")

            else:
                raise Exception(f"OS non supporté: {System}")

            # Vérifie que l'exécutable existe
            if not os.path.exists(self.ExecutablePath):
                raise Exception(f"Exécutable Real-ESRGAN non trouvé: {self.ExecutablePath}")

            # Rend l'exécutable... exécutable (Linux)
            if System == "Linux":
                os.chmod(self.ExecutablePath, 0o755)

            self.Logger.info(f"Real-ESRGAN détecté: {self.ExecutablePath}")
            self.Logger.info(f"Modèles: {self.ModelsPath}")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la détection de Real-ESRGAN: {e}")
            raise

    def SetPerformanceConfig(self, Config: Dict):
        """
        Met à jour la configuration de performance

        Args:
            Config: Nouvelle configuration de performance
        """
        self.PerformanceConfig = Config or {}
        self.Logger.info("Configuration de performance mise à jour")

    def _BuildCommand(self, InputPath: str, OutputPath: str,
                     ScaleFactor: int, Model: str) -> List[str]:
        """
        Construit la commande Real-ESRGAN avec les options de performance

        Args:
            InputPath: Chemin de l'image d'entrée
            OutputPath: Chemin de l'image de sortie
            ScaleFactor: Facteur d'upscaling
            Model: Nom du modèle

        Returns:
            Liste des arguments de la commande
        """
        Command = [
            self.ExecutablePath,
            '-i', InputPath,
            '-o', OutputPath,
            '-s', str(ScaleFactor),
            '-n', Model
        ]

        # Tile size (-t)
        TileSize = self.PerformanceConfig.get('tile_size')
        if TileSize and TileSize > 0:
            # Supporte le format string pour multi-GPU (ex: "256,256")
            if isinstance(TileSize, str):
                Command.extend(['-t', TileSize])
            else:
                Command.extend(['-t', str(TileSize)])

        # GPU selection (-g)
        GpuIds = self.PerformanceConfig.get('gpu_ids')
        if GpuIds:
            if isinstance(GpuIds, list):
                GpuStr = ','.join(map(str, GpuIds))
            else:
                GpuStr = str(GpuIds)
            Command.extend(['-g', GpuStr])

        # Threads (-j) format: "load:proc:save" ou "1:2,2:2" pour multi-GPU
        Threads = self.PerformanceConfig.get('threads')
        if Threads:
            if isinstance(Threads, str):
                # Format déjà prêt (ex: "1:2:2")
                Command.extend(['-j', Threads])
            elif isinstance(Threads, dict):
                # Format dictionnaire
                Load = Threads.get('load', 1)
                Process = Threads.get('process', 2)
                Save = Threads.get('save', 2)
                Command.extend(['-j', f"{Load}:{Process}:{Save}"])

        # TTA mode (-x) - meilleure qualité mais plus lent
        if self.PerformanceConfig.get('tta_mode', False):
            Command.append('-x')

        # Format de sortie (-f)
        OutputFormat = self.PerformanceConfig.get('output_format')
        if OutputFormat and OutputFormat != 'png':
            Command.extend(['-f', OutputFormat])

        return Command

    def UpscaleImage(self, InputPath: str, OutputPath: str,
                    ScaleFactor: int = 4, Model: str = "realesr-animevideov3") -> bool:
        """
        Upscale une image unique

        Args:
            InputPath: Chemin de l'image d'entrée
            OutputPath: Chemin de l'image de sortie
            ScaleFactor: Facteur d'upscaling (2, 3, ou 4)
            Model: Nom du modèle à utiliser

        Returns:
            True si succès
        """
        try:
            # Valide le facteur d'upscaling
            if ScaleFactor not in ProcessingConfig.SUPPORTED_UPSCALE_FACTORS:
                self.Logger.error(f"Facteur d'upscaling non supporté: {ScaleFactor}")
                return False

            # Construit la commande avec les options de performance
            Command = self._BuildCommand(InputPath, OutputPath, ScaleFactor, Model)

            self.Logger.debug(f"Commande: {' '.join(Command)}")

            # Exécute
            Result = subprocess.run(
                Command,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.ExecutablePath)  # Important pour trouver les modèles
            )

            if Result.returncode == 0:
                self.Logger.debug(f"✓ Image upscalée: {os.path.basename(OutputPath)}")
                return True
            else:
                self.Logger.error(f"Erreur Real-ESRGAN: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling: {e}")
            return False

    def UpscaleBatchList(self, ImagePaths: List[str], OutputDir: str,
                        ScaleFactor: int = 4, Model: str = "realesr-animevideov3",
                        ProgressCallback=None) -> List[str]:
        """
        Upscale une liste d'images en mode dossier (une seule commande Real-ESRGAN)

        Args:
            ImagePaths: Liste des chemins d'images (doivent être dans le même dossier)
            OutputDir: Répertoire de sortie
            ScaleFactor: Facteur d'upscaling
            Model: Nom du modèle
            ProgressCallback: Fonction appelée à la fin (total, total)

        Returns:
            Liste des chemins des images upscalées
        """
        if not ImagePaths:
            return []

        try:
            os.makedirs(OutputDir, exist_ok=True)
            Total = len(ImagePaths)

            # Récupère le dossier d'entrée depuis le premier fichier
            InputDir = os.path.dirname(ImagePaths[0])

            self.Logger.info(f"Upscaling dossier: {InputDir} -> {OutputDir} ({Total} images)")

            # Utilise le mode dossier de Real-ESRGAN (une seule commande)
            Success = self.UpscaleDirectory(InputDir, OutputDir, ScaleFactor, Model)

            if not Success:
                self.Logger.error("Échec de l'upscaling en mode dossier")
                return []

            # Liste les images upscalées
            UpscaledImages = []
            for ImagePath in ImagePaths:
                Basename = os.path.basename(ImagePath)
                OutputPath = os.path.join(OutputDir, Basename)

                if os.path.exists(OutputPath):
                    UpscaledImages.append(OutputPath)
                else:
                    self.Logger.warning(f"Image manquante après upscaling: {Basename}")

            # Callback de progression (appelé une fois à la fin)
            if ProgressCallback:
                ProgressCallback(Total, Total)

            self.Logger.info(f"✓ {len(UpscaledImages)}/{Total} images upscalées avec succès")
            return UpscaledImages

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling de la liste: {e}")
            return []

    def UpscaleDirectory(self, InputDir: str, OutputDir: str,
                        ScaleFactor: int = 4, Model: str = "realesr-animevideov3") -> bool:
        """
        Upscale toutes les images d'un dossier en une seule commande

        Args:
            InputDir: Dossier contenant les images d'entrée
            OutputDir: Dossier de sortie
            ScaleFactor: Facteur d'upscaling (2, 3, ou 4)
            Model: Nom du modèle à utiliser

        Returns:
            True si succès
        """
        try:
            # Valide le facteur d'upscaling
            if ScaleFactor not in ProcessingConfig.SUPPORTED_UPSCALE_FACTORS:
                self.Logger.error(f"Facteur d'upscaling non supporté: {ScaleFactor}")
                return False

            os.makedirs(OutputDir, exist_ok=True)

            # Construit la commande en mode dossier
            Command = self._BuildCommand(InputDir, OutputDir, ScaleFactor, Model)

            self.Logger.debug(f"Commande: {' '.join(Command)}")

            # Exécute Real-ESRGAN
            Result = subprocess.run(
                Command,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.ExecutablePath)
            )

            if Result.returncode == 0:
                self.Logger.info(f"✓ Dossier upscalé: {InputDir}")
                return True
            else:
                self.Logger.error(f"Erreur Real-ESRGAN: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling du dossier: {e}")
            return False

    def ValidateModel(self, ModelName: str) -> bool:
        """
        Vérifie qu'un modèle est disponible

        Args:
            ModelName: Nom du modèle

        Returns:
            True si le modèle existe
        """
        ParamPath = os.path.join(self.ModelsPath, f"{ModelName}.param")
        BinPath = os.path.join(self.ModelsPath, f"{ModelName}.bin")

        return os.path.exists(ParamPath) and os.path.exists(BinPath)
