"""
Gestionnaire Real-CUGAN pour l'upscaling d'images (côté serveur)
Utilise les exécutables portables fournis
"""

import os
import subprocess
import platform
from typing import Optional, List
from pathlib import Path

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import ProcessingConfig


class RealCUGANHandler:
    """Gestionnaire Real-CUGAN pour upscaling côté serveur"""

    # Modèles disponibles par variante
    MODEL_VARIANTS = {
        'models-se': {
            'name': 'Standard Edition',
            'scales': [2, 3, 4],
            'denoise_levels': [-1, 0, 1, 2, 3]
        },
        'models-pro': {
            'name': 'Pro',
            'scales': [2, 3],
            'denoise_levels': [-1, 0, 3]
        },
        'models-nose': {
            'name': 'Nose (léger)',
            'scales': [2],
            'denoise_levels': [-1]
        }
    }

    def __init__(self, ProjectRoot: Optional[str] = None):
        """
        Initialise le gestionnaire Real-CUGAN

        Args:
            ProjectRoot: Racine du projet (détecté auto si None)
        """
        self.Logger = GetModuleLogger("RealCUGANHandler")
        self.ProjectRoot = ProjectRoot or self._DetectProjectRoot()
        self.ExecutablePath = None
        self.ModelsBasePath = None

        self._DetectExecutable()

    def _DetectProjectRoot(self) -> str:
        """Détecte la racine du projet"""
        CurrentPath = Path(__file__).resolve()
        ProjectRoot = CurrentPath.parent.parent.parent
        self.Logger.debug(f"Racine du projet détectée: {ProjectRoot}")
        return str(ProjectRoot)

    def _DetectExecutable(self):
        """Détecte l'exécutable Real-CUGAN selon l'OS"""
        try:
            System = platform.system()

            if System == "Linux":
                ExecDir = os.path.join(self.ProjectRoot, "realcugan-ncnn-vulkan-20220728-ubuntu")
                ExecName = "realcugan-ncnn-vulkan"
                self.ExecutablePath = os.path.join(ExecDir, ExecName)
                self.ModelsBasePath = ExecDir

            elif System == "Windows":
                ExecDir = os.path.join(self.ProjectRoot, "realcugan-ncnn-vulkan-20220728-windows")
                ExecName = "realcugan-ncnn-vulkan.exe"
                self.ExecutablePath = os.path.join(ExecDir, ExecName)
                self.ModelsBasePath = ExecDir

            else:
                raise Exception(f"OS non supporté: {System}")

            if not os.path.exists(self.ExecutablePath):
                raise Exception(f"Exécutable Real-CUGAN non trouvé: {self.ExecutablePath}")

            if System == "Linux":
                os.chmod(self.ExecutablePath, 0o755)

            self.Logger.info(f"Real-CUGAN détecté: {self.ExecutablePath}")
            self.Logger.info(f"Modèles: {self.ModelsBasePath}")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la détection de Real-CUGAN: {e}")
            raise

    def GetAvailableModels(self) -> List[str]:
        """
        Liste les variantes de modèles disponibles

        Returns:
            Liste des variantes (models-se, models-pro, models-nose)
        """
        Available = []
        for Variant in self.MODEL_VARIANTS.keys():
            VariantPath = os.path.join(self.ModelsBasePath, Variant)
            if os.path.exists(VariantPath):
                Available.append(Variant)
        return Available

    def UpscaleImage(self, InputPath: str, OutputPath: str,
                    ScaleFactor: int = 2, ModelVariant: str = "models-se",
                    DenoiseLevel: int = -1) -> bool:
        """
        Upscale une image unique

        Args:
            InputPath: Chemin de l'image d'entrée
            OutputPath: Chemin de l'image de sortie
            ScaleFactor: Facteur d'upscaling (2, 3, ou 4)
            ModelVariant: Variante de modèle
            DenoiseLevel: Niveau de débruitage (-1/0/1/2/3)

        Returns:
            True si succès
        """
        try:
            if ScaleFactor not in ProcessingConfig.SUPPORTED_UPSCALE_FACTORS:
                self.Logger.error(f"Facteur d'upscaling non supporté: {ScaleFactor}")
                return False

            ModelPath = os.path.join(self.ModelsBasePath, ModelVariant)

            Command = [
                self.ExecutablePath,
                '-i', InputPath,
                '-o', OutputPath,
                '-s', str(ScaleFactor),
                '-n', str(DenoiseLevel),
                '-m', ModelPath
            ]

            Result = subprocess.run(
                Command,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.ExecutablePath)
            )

            if Result.returncode == 0:
                self.Logger.debug(f"✓ Image upscalée: {os.path.basename(OutputPath)}")
                return True
            else:
                self.Logger.error(f"Erreur Real-CUGAN: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling: {e}")
            return False

    def UpscaleBatch(self, InputDir: str, OutputDir: str,
                    ScaleFactor: int = 2, ModelVariant: str = "models-se",
                    DenoiseLevel: int = -1) -> bool:
        """
        Upscale un répertoire d'images

        Args:
            InputDir: Répertoire contenant les images
            OutputDir: Répertoire de sortie
            ScaleFactor: Facteur d'upscaling
            ModelVariant: Variante de modèle
            DenoiseLevel: Niveau de débruitage

        Returns:
            True si succès
        """
        try:
            os.makedirs(OutputDir, exist_ok=True)

            if ScaleFactor not in ProcessingConfig.SUPPORTED_UPSCALE_FACTORS:
                self.Logger.error(f"Facteur d'upscaling non supporté: {ScaleFactor}")
                return False

            ModelPath = os.path.join(self.ModelsBasePath, ModelVariant)

            Command = [
                self.ExecutablePath,
                '-i', InputDir,
                '-o', OutputDir,
                '-s', str(ScaleFactor),
                '-n', str(DenoiseLevel),
                '-m', ModelPath,
                '-f', 'png'
            ]

            self.Logger.info(f"Upscaling du répertoire {InputDir}...")
            self.Logger.info(f"Modèle: {ModelVariant}, Facteur: x{ScaleFactor}, Denoise: {DenoiseLevel}")

            Result = subprocess.run(
                Command,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.ExecutablePath)
            )

            if Result.returncode == 0:
                self.Logger.info(f"✓ Répertoire upscalé avec succès")
                return True
            else:
                self.Logger.error(f"Erreur Real-CUGAN: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling du répertoire: {e}")
            return False

    def ValidateModel(self, ModelVariant: str, ScaleFactor: int = 2) -> bool:
        """
        Vérifie qu'une variante de modèle est disponible pour un facteur donné

        Args:
            ModelVariant: Variante de modèle (models-se, models-pro, models-nose)
            ScaleFactor: Facteur d'upscaling

        Returns:
            True si le modèle existe et supporte ce facteur
        """
        if ModelVariant not in self.MODEL_VARIANTS:
            return False

        VariantInfo = self.MODEL_VARIANTS[ModelVariant]
        if ScaleFactor not in VariantInfo['scales']:
            return False

        ModelPath = os.path.join(self.ModelsBasePath, ModelVariant)
        return os.path.exists(ModelPath)

    def TestUpscaling(self, TestImagePath: str, OutputPath: str) -> bool:
        """
        Test rapide de l'upscaling

        Args:
            TestImagePath: Image de test
            OutputPath: Chemin de sortie

        Returns:
            True si le test réussit
        """
        return self.UpscaleImage(
            TestImagePath,
            OutputPath,
            ScaleFactor=2,
            ModelVariant="models-se",
            DenoiseLevel=-1
        )
