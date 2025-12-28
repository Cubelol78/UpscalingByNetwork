"""
Gestionnaire Real-ESRGAN pour l'upscaling d'images
Utilise les exécutables portables fournis
"""

import os
import subprocess
import platform
from typing import Optional, List
from pathlib import Path

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import ProcessingConfig


class RealESRGANHandler:
    """Gestionnaire Real-ESRGAN pour upscaling"""

    def __init__(self, ProjectRoot: Optional[str] = None):
        """
        Initialise le gestionnaire Real-ESRGAN

        Args:
            ProjectRoot: Racine du projet (détecté auto si None)
        """
        self.Logger = GetModuleLogger("RealESRGANHandler")
        self.ProjectRoot = ProjectRoot or self._DetectProjectRoot()
        self.ExecutablePath = None
        self.ModelsPath = None

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

        # Remonte de server/utils vers la racine
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

    def GetAvailableModels(self) -> List[str]:
        """
        Liste les modèles disponibles

        Returns:
            Liste des noms de modèles
        """
        try:
            if not os.path.exists(self.ModelsPath):
                return []

            # Liste les fichiers .param (chaque modèle a un .param et un .bin)
            Models = set()
            for File in os.listdir(self.ModelsPath):
                if File.endswith('.param'):
                    ModelName = File.replace('.param', '')
                    Models.add(ModelName)

            return sorted(list(Models))

        except Exception as e:
            self.Logger.error(f"Erreur lors de la liste des modèles: {e}")
            return []

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

            # Construit la commande
            Command = [
                self.ExecutablePath,
                '-i', InputPath,
                '-o', OutputPath,
                '-s', str(ScaleFactor),
                '-n', Model
            ]

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

    def UpscaleBatch(self, InputDir: str, OutputDir: str,
                    ScaleFactor: int = 4, Model: str = "realesr-animevideov3") -> bool:
        """
        Upscale un répertoire d'images

        Args:
            InputDir: Répertoire contenant les images
            OutputDir: Répertoire de sortie
            ScaleFactor: Facteur d'upscaling
            Model: Nom du modèle

        Returns:
            True si succès
        """
        try:
            # Crée le répertoire de sortie
            os.makedirs(OutputDir, exist_ok=True)

            # Valide le facteur d'upscaling
            if ScaleFactor not in ProcessingConfig.SUPPORTED_UPSCALE_FACTORS:
                self.Logger.error(f"Facteur d'upscaling non supporté: {ScaleFactor}")
                return False

            # Construit la commande
            Command = [
                self.ExecutablePath,
                '-i', InputDir,
                '-o', OutputDir,
                '-s', str(ScaleFactor),
                '-n', Model,
                '-f', 'png'  # Format de sortie
            ]

            self.Logger.info(f"Upscaling du répertoire {InputDir}...")
            self.Logger.info(f"Modèle: {Model}, Facteur: x{ScaleFactor}")

            # Exécute
            Result = subprocess.run(
                Command,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.ExecutablePath)
            )

            if Result.returncode == 0:
                # Compte les images traitées
                OutputImages = [f for f in os.listdir(OutputDir) if f.endswith('.png')]
                self.Logger.info(f"✓ {len(OutputImages)} images upscalées")
                return True
            else:
                self.Logger.error(f"Erreur Real-ESRGAN: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling batch: {e}")
            return False

    def UpscaleBatchList(self, ImagePaths: List[str], OutputDir: str,
                        ScaleFactor: int = 4, Model: str = "realesr-animevideov3",
                        ProgressCallback=None) -> List[str]:
        """
        Upscale une liste d'images avec callback de progression

        Args:
            ImagePaths: Liste des chemins d'images
            OutputDir: Répertoire de sortie
            ScaleFactor: Facteur d'upscaling
            Model: Nom du modèle
            ProgressCallback: Fonction appelée pour chaque image (image_index, total)

        Returns:
            Liste des chemins des images upscalées
        """
        try:
            os.makedirs(OutputDir, exist_ok=True)

            UpscaledImages = []
            Total = len(ImagePaths)

            for Index, InputPath in enumerate(ImagePaths):
                # Génère le nom de sortie
                Basename = os.path.basename(InputPath)
                OutputPath = os.path.join(OutputDir, Basename)

                # Upscale l'image
                Success = self.UpscaleImage(InputPath, OutputPath, ScaleFactor, Model)

                if Success:
                    UpscaledImages.append(OutputPath)

                # Callback de progression
                if ProgressCallback:
                    ProgressCallback(Index + 1, Total)

            self.Logger.info(f"✓ {len(UpscaledImages)}/{Total} images upscalées avec succès")
            return UpscaledImages

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling de la liste: {e}")
            return []

    def TestUpscaling(self, TestImagePath: str, OutputPath: str) -> bool:
        """
        Test rapide de l'upscaling

        Args:
            TestImagePath: Chemin de l'image de test
            OutputPath: Chemin de sortie

        Returns:
            True si succès
        """
        self.Logger.info("Test de l'upscaling Real-ESRGAN...")

        if not os.path.exists(TestImagePath):
            self.Logger.error(f"Image de test non trouvée: {TestImagePath}")
            return False

        Success = self.UpscaleImage(
            TestImagePath,
            OutputPath,
            ScaleFactor=2,
            Model="realesrgan-x4plus"
        )

        if Success:
            self.Logger.info(f"✓ Test réussi! Image de sortie: {OutputPath}")
        else:
            self.Logger.error("✗ Test échoué")

        return Success

    def GetModelPath(self, ModelName: str) -> Optional[str]:
        """
        Récupère le chemin complet d'un modèle

        Args:
            ModelName: Nom du modèle

        Returns:
            Chemin du fichier .param ou None
        """
        ParamPath = os.path.join(self.ModelsPath, f"{ModelName}.param")

        if os.path.exists(ParamPath):
            return ParamPath

        return None

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


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    # Test du gestionnaire Real-ESRGAN
    Handler = RealESRGANHandler()

    print("\n=== Test RealESRGANHandler ===")
    print(f"Exécutable: {Handler.ExecutablePath}")
    print(f"Modèles: {Handler.ModelsPath}")

    # Liste les modèles disponibles
    Models = Handler.GetAvailableModels()
    print(f"\nModèles disponibles ({len(Models)}):")
    for Model in Models:
        IsValid = Handler.ValidateModel(Model)
        print(f"  - {Model} {'✓' if IsValid else '✗'}")

    # Test avec une image (si disponible)
    TestImage = "test.png"
    if os.path.exists(TestImage):
        print(f"\nTest d'upscaling avec {TestImage}")
        Handler.TestUpscaling(TestImage, "test_upscaled.png")
    else:
        print(f"\n⚠ Image de test {TestImage} non trouvée")
