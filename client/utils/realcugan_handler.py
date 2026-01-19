"""
Gestionnaire Real-CUGAN pour l'upscaling d'images (côté client)
Utilise les exécutables portables fournis
Supporte les options de performance: tile-size, GPU selection, threads, TTA, denoise
"""

import os
import subprocess
import platform
import time
import threading
from typing import Optional, List, Dict, Tuple
from pathlib import Path

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import ProcessingConfig


class RealCUGANHandler:
    """Gestionnaire Real-CUGAN pour upscaling avec options de performance et débruitage"""

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

    def __init__(self, ProjectRoot: Optional[str] = None, PerformanceConfig: Optional[Dict] = None):
        """
        Initialise le gestionnaire Real-CUGAN

        Args:
            ProjectRoot: Racine du projet (détecté auto si None)
            PerformanceConfig: Configuration de performance (tile_size, gpu_ids, threads, tta_mode)
        """
        self.Logger = GetModuleLogger("RealCUGANHandler")
        self.ProjectRoot = ProjectRoot or self._DetectProjectRoot()
        self.ExecutablePath = None
        self.ModelsBasePath = None  # Dossier contenant models-se, models-pro, etc.
        self.PerformanceConfig = PerformanceConfig or {}

        # Détecte l'exécutable approprié
        self._DetectExecutable()

    def _DetectProjectRoot(self) -> str:
        """
        Détecte la racine du projet

        Returns:
            Chemin vers la racine du projet
        """
        # Remonte jusqu'à trouver le dossier contenant les executables
        CurrentPath = Path(__file__).resolve()

        # Remonte de client/utils vers la racine
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

            # Vérifie que l'exécutable existe
            if not os.path.exists(self.ExecutablePath):
                raise Exception(f"Exécutable Real-CUGAN non trouvé: {self.ExecutablePath}")

            # Rend l'exécutable... exécutable (Linux)
            if System == "Linux":
                os.chmod(self.ExecutablePath, 0o755)

            self.Logger.info(f"Real-CUGAN détecté: {self.ExecutablePath}")
            self.Logger.info(f"Modèles: {self.ModelsBasePath}")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la détection de Real-CUGAN: {e}")
            raise

    def SetPerformanceConfig(self, Config: Dict):
        """
        Met à jour la configuration de performance

        Args:
            Config: Nouvelle configuration de performance
        """
        self.PerformanceConfig = Config or {}
        self.Logger.info("Configuration de performance mise à jour")

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

    def _BuildCommand(self, InputPath: str, OutputPath: str,
                     ScaleFactor: int, ModelVariant: str = "models-se",
                     DenoiseLevel: int = -1) -> List[str]:
        """
        Construit la commande Real-CUGAN avec les options de performance

        Args:
            InputPath: Chemin de l'image d'entrée
            OutputPath: Chemin de l'image de sortie
            ScaleFactor: Facteur d'upscaling (2, 3, 4)
            ModelVariant: Variante de modèle (models-se, models-pro, models-nose)
            DenoiseLevel: Niveau de débruitage (-1=auto, 0=off, 1/2/3=niveaux)

        Returns:
            Liste des arguments de la commande
        """
        # Chemin vers le dossier du modèle
        ModelPath = os.path.join(self.ModelsBasePath, ModelVariant)

        Command = [
            self.ExecutablePath,
            '-i', InputPath,
            '-o', OutputPath,
            '-s', str(ScaleFactor),
            '-n', str(DenoiseLevel),
            '-m', ModelPath
        ]

        # GPU selection (-g)
        GpuIds = self.PerformanceConfig.get('gpu_ids', [])
        GpuCount = 0
        if GpuIds:
            if isinstance(GpuIds, list):
                GpuCount = len(GpuIds)
                GpuStr = ','.join(map(str, GpuIds))
            else:
                GpuCount = 1
                GpuStr = str(GpuIds)
            Command.extend(['-g', GpuStr])

        # Tile size (-t)
        TileSize = self.PerformanceConfig.get('tile_size', 0)
        try:
            if isinstance(TileSize, str):
                TileSize = int(TileSize) if TileSize.strip() else 0
            if isinstance(TileSize, int) and TileSize > 0:
                if GpuCount > 1:
                    TileSizeStr = ','.join([str(TileSize)] * GpuCount)
                else:
                    TileSizeStr = str(TileSize)
                Command.extend(['-t', TileSizeStr])
        except (ValueError, TypeError):
            self.Logger.warning(f"Tile size invalide ignoré: {TileSize}")

        # Threads (-j)
        Threads = self.PerformanceConfig.get('threads')
        if Threads:
            try:
                if isinstance(Threads, str) and Threads.strip():
                    Command.extend(['-j', Threads.strip()])
                elif isinstance(Threads, dict):
                    Load = int(Threads.get('load', 1)) or 1
                    Process = int(Threads.get('process', 2)) or 2
                    Save = int(Threads.get('save', 2)) or 2
                    if GpuCount > 1:
                        ProcessStr = ','.join([str(Process)] * GpuCount)
                        Command.extend(['-j', f"{Load}:{ProcessStr}:{Save}"])
                    else:
                        Command.extend(['-j', f"{Load}:{Process}:{Save}"])
            except (ValueError, TypeError) as e:
                self.Logger.warning(f"Configuration threads invalide ignorée: {Threads} - {e}")

        # TTA mode (-x)
        if self.PerformanceConfig.get('tta_mode', False):
            Command.append('-x')

        # Format de sortie (-f)
        OutputFormat = self.PerformanceConfig.get('output_format')
        if OutputFormat and OutputFormat != 'png':
            Command.extend(['-f', OutputFormat])

        return Command

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
            DenoiseLevel: Niveau de débruitage

        Returns:
            True si succès
        """
        try:
            # Valide le facteur d'upscaling
            if ScaleFactor not in ProcessingConfig.SUPPORTED_UPSCALE_FACTORS:
                self.Logger.error(f"Facteur d'upscaling non supporté: {ScaleFactor}")
                return False

            # Construit la commande
            Command = self._BuildCommand(InputPath, OutputPath, ScaleFactor,
                                        ModelVariant, DenoiseLevel)

            self.Logger.debug(f"Commande: {' '.join(Command)}")

            # Exécute
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

    def UpscaleBatchList(self, ImagePaths: List[str], OutputDir: str,
                        ScaleFactor: int = 2, ModelVariant: str = "models-se",
                        DenoiseLevel: int = -1,
                        ProgressCallback=None) -> Tuple[List[str], str]:
        """
        Upscale une liste d'images en mode dossier

        Args:
            ImagePaths: Liste des chemins d'images
            OutputDir: Répertoire de sortie
            ScaleFactor: Facteur d'upscaling
            ModelVariant: Variante de modèle
            DenoiseLevel: Niveau de débruitage
            ProgressCallback: Fonction appelée pour chaque image traitée

        Returns:
            Tuple (UpscaledImages, ErrorDetails)
        """
        if not ImagePaths:
            return [], ""

        try:
            os.makedirs(OutputDir, exist_ok=True)
            Total = len(ImagePaths)

            # Récupère le dossier d'entrée depuis le premier fichier
            InputDir = os.path.dirname(ImagePaths[0])

            self.Logger.info(f"Upscaling dossier: {InputDir} -> {OutputDir} ({Total} images)")

            # Utilise le mode dossier
            Success, ErrorDetails = self.UpscaleDirectory(
                InputDir, OutputDir, ScaleFactor, ModelVariant, DenoiseLevel,
                TotalImages=Total, ProgressCallback=ProgressCallback
            )

            if not Success:
                self.Logger.error("Échec de l'upscaling en mode dossier")
                return [], ErrorDetails

            # Liste les images upscalées
            UpscaledImages = []
            for ImagePath in ImagePaths:
                Basename = os.path.basename(ImagePath)
                OutputPath = os.path.join(OutputDir, Basename)

                if os.path.exists(OutputPath):
                    UpscaledImages.append(OutputPath)
                else:
                    self.Logger.warning(f"Image manquante après upscaling: {Basename}")

            self.Logger.info(f"✓ {len(UpscaledImages)}/{Total} images upscalées avec succès")
            return UpscaledImages, ""

        except Exception as e:
            ErrorMsg = f"Erreur lors de l'upscaling de la liste: {e}"
            self.Logger.error(ErrorMsg)
            return [], ErrorMsg

    def UpscaleDirectory(self, InputDir: str, OutputDir: str,
                        ScaleFactor: int = 2, ModelVariant: str = "models-se",
                        DenoiseLevel: int = -1,
                        TotalImages: int = None, ProgressCallback=None) -> Tuple[bool, str]:
        """
        Upscale toutes les images d'un dossier

        Args:
            InputDir: Dossier contenant les images d'entrée
            OutputDir: Dossier de sortie
            ScaleFactor: Facteur d'upscaling
            ModelVariant: Variante de modèle
            DenoiseLevel: Niveau de débruitage
            TotalImages: Nombre total d'images
            ProgressCallback: Fonction appelée pour chaque image

        Returns:
            Tuple (Success, ErrorDetails)
        """
        try:
            if ScaleFactor not in ProcessingConfig.SUPPORTED_UPSCALE_FACTORS:
                ErrorMsg = f"Facteur d'upscaling non supporté: {ScaleFactor}"
                self.Logger.error(ErrorMsg)
                return False, ErrorMsg

            os.makedirs(OutputDir, exist_ok=True)

            # Construit la commande en mode dossier
            Command = self._BuildCommand(InputDir, OutputDir, ScaleFactor,
                                         ModelVariant, DenoiseLevel)

            self.Logger.info(f"Commande Real-CUGAN: {' '.join(Command)}")

            # Thread de surveillance du dossier de sortie
            StopMonitoring = threading.Event()
            MonitoredCount = [0]

            def MonitorOutputDirectory():
                LastCount = 0
                LastLogTime = time.time()

                while not StopMonitoring.is_set():
                    try:
                        if os.path.exists(OutputDir):
                            Files = [f for f in os.listdir(OutputDir)
                                    if os.path.isfile(os.path.join(OutputDir, f))]
                            CurrentCount = len(Files)

                            if CurrentCount > LastCount:
                                MonitoredCount[0] = CurrentCount
                                LastCount = CurrentCount

                                if TotalImages:
                                    Progress = (CurrentCount / TotalImages) * 100
                                    print(f"\r⟳ Progression: {CurrentCount}/{TotalImages} images ({Progress:.1f}%)",
                                          end='', flush=True)

                                    CurrentTime = time.time()
                                    if CurrentCount % 10 == 0 or (CurrentTime - LastLogTime) >= 5:
                                        print()
                                        self.Logger.info(f"⟳ Progression: {CurrentCount}/{TotalImages} images ({Progress:.1f}%)")
                                        LastLogTime = CurrentTime
                                else:
                                    print(f"\r⟳ Progression: {CurrentCount} images", end='', flush=True)

                                if ProgressCallback:
                                    ProgressCallback(CurrentCount, TotalImages or CurrentCount)

                        time.sleep(0.5)
                    except Exception as e:
                        self.Logger.debug(f"Erreur monitoring: {e}")
                        break

            MonitorThread = threading.Thread(target=MonitorOutputDirectory, daemon=True)
            MonitorThread.start()

            # Exécute Real-CUGAN
            Process = subprocess.Popen(
                Command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=os.path.dirname(self.ExecutablePath)
            )

            AllOutput = []
            FirstLines = 0

            for Line in iter(Process.stdout.readline, ''):
                if not Line:
                    break

                Line = Line.strip()
                AllOutput.append(Line)

                if not Line:
                    continue

                if FirstLines < 5:
                    self.Logger.info(f"[Real-CUGAN] {Line}")
                    FirstLines += 1

            ReturnCode = Process.wait()

            StopMonitoring.set()
            MonitorThread.join(timeout=2)

            print()

            CurrentImage = MonitoredCount[0]

            if ReturnCode == 0:
                if TotalImages:
                    self.Logger.info(f"✓ Real-CUGAN terminé: {CurrentImage}/{TotalImages} images upscalées")
                else:
                    self.Logger.info(f"✓ Real-CUGAN terminé: {CurrentImage} images upscalées")
                return True, ""
            else:
                ErrorMsg = '\n'.join(AllOutput[-10:]) if AllOutput else "Erreur inconnue"
                self.Logger.error(f"Erreur Real-CUGAN (code {ReturnCode}): {ErrorMsg}")
                return False, ErrorMsg

        except Exception as e:
            ErrorMsg = f"Erreur lors de l'upscaling du dossier: {e}"
            self.Logger.error(ErrorMsg)
            return False, ErrorMsg

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
