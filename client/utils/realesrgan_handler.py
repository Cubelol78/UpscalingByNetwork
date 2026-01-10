"""
Gestionnaire Real-ESRGAN pour l'upscaling d'images (côté client)
Utilise les exécutables portables fournis
Supporte les options de performance: tile-size, GPU selection, threads, TTA
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

        # GPU selection (-g) - détecte d'abord le nombre de GPU
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

        # Tile size (-t) - dupliqué pour chaque GPU si multi-GPU
        TileSize = self.PerformanceConfig.get('tile_size', 0)
        try:
            # Convertit en int si c'est une chaîne
            if isinstance(TileSize, str):
                TileSize = int(TileSize) if TileSize.strip() else 0
            # Valide que c'est un entier positif
            if isinstance(TileSize, int) and TileSize > 0:
                if GpuCount > 1:
                    # Multi-GPU: répète le tile size pour chaque GPU
                    TileSizeStr = ','.join([str(TileSize)] * GpuCount)
                else:
                    TileSizeStr = str(TileSize)
                Command.extend(['-t', TileSizeStr])
        except (ValueError, TypeError):
            # Ignore les valeurs invalides
            self.Logger.warning(f"Tile size invalide ignoré: {TileSize}")

        # Threads (-j) format: "load:proc:save" ou "load:proc,proc:save" pour multi-GPU
        Threads = self.PerformanceConfig.get('threads')
        if Threads:
            try:
                if isinstance(Threads, str) and Threads.strip():
                    # Format déjà prêt (ex: "1:2:2")
                    Command.extend(['-j', Threads.strip()])
                elif isinstance(Threads, dict):
                    # Format dictionnaire - valide les valeurs
                    Load = int(Threads.get('load', 1)) or 1
                    Process = int(Threads.get('process', 2)) or 2
                    Save = int(Threads.get('save', 2)) or 2
                    if GpuCount > 1:
                        # Multi-GPU: format "load:proc,proc,...:save"
                        ProcessStr = ','.join([str(Process)] * GpuCount)
                        Command.extend(['-j', f"{Load}:{ProcessStr}:{Save}"])
                    else:
                        Command.extend(['-j', f"{Load}:{Process}:{Save}"])
            except (ValueError, TypeError) as e:
                self.Logger.warning(f"Configuration threads invalide ignorée: {Threads} - {e}")

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
                        ProgressCallback=None) -> Tuple[List[str], str]:
        """
        Upscale une liste d'images en mode dossier (une seule commande Real-ESRGAN)

        Args:
            ImagePaths: Liste des chemins d'images (doivent être dans le même dossier)
            OutputDir: Répertoire de sortie
            ScaleFactor: Facteur d'upscaling
            Model: Nom du modèle
            ProgressCallback: Fonction appelée pour chaque image traitée (current, total)

        Returns:
            Tuple (UpscaledImages, ErrorDetails):
                - UpscaledImages: Liste des chemins des images upscalées
                - ErrorDetails: Message d'erreur si échec, chaîne vide sinon
        """
        if not ImagePaths:
            return [], ""

        try:
            os.makedirs(OutputDir, exist_ok=True)
            Total = len(ImagePaths)

            # Récupère le dossier d'entrée depuis le premier fichier
            InputDir = os.path.dirname(ImagePaths[0])

            self.Logger.info(f"Upscaling dossier: {InputDir} -> {OutputDir} ({Total} images)")

            # Utilise le mode dossier de Real-ESRGAN (une seule commande) avec callback
            Success, ErrorDetails = self.UpscaleDirectory(
                InputDir, OutputDir, ScaleFactor, Model,
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
                        ScaleFactor: int = 4, Model: str = "realesr-animevideov3",
                        TotalImages: int = None, ProgressCallback=None) -> Tuple[bool, str]:
        """
        Upscale toutes les images d'un dossier en une seule commande avec suivi en temps réel

        Args:
            InputDir: Dossier contenant les images d'entrée
            OutputDir: Dossier de sortie
            ScaleFactor: Facteur d'upscaling (2, 3, ou 4)
            Model: Nom du modèle à utiliser
            TotalImages: Nombre total d'images (pour calculer le pourcentage)
            ProgressCallback: Fonction appelée pour chaque image (current, total)

        Returns:
            Tuple (Success, ErrorDetails):
                - Success: True si succès
                - ErrorDetails: Message d'erreur stderr si échec, chaîne vide sinon
        """
        try:
            # Valide le facteur d'upscaling
            if ScaleFactor not in ProcessingConfig.SUPPORTED_UPSCALE_FACTORS:
                ErrorMsg = f"Facteur d'upscaling non supporté: {ScaleFactor}"
                self.Logger.error(ErrorMsg)
                return False, ErrorMsg

            os.makedirs(OutputDir, exist_ok=True)

            # Construit la commande en mode dossier
            Command = self._BuildCommand(InputDir, OutputDir, ScaleFactor, Model)

            # Log la commande complète pour diagnostic
            self.Logger.info(f"Commande Real-ESRGAN: {' '.join(Command)}")

            # Fonction qui surveille le dossier de sortie pour compter les images traitées
            StopMonitoring = threading.Event()
            MonitoredCount = [0]  # Liste mutable pour partager entre threads

            def MonitorOutputDirectory():
                """Surveille le dossier de sortie et compte les fichiers créés"""
                LastCount = 0
                LastLogTime = time.time()

                while not StopMonitoring.is_set():
                    try:
                        # Compte les fichiers dans le dossier de sortie
                        if os.path.exists(OutputDir):
                            Files = [f for f in os.listdir(OutputDir) if os.path.isfile(os.path.join(OutputDir, f))]
                            CurrentCount = len(Files)

                            if CurrentCount > LastCount:
                                MonitoredCount[0] = CurrentCount
                                LastCount = CurrentCount

                                # Affiche la progression en temps réel
                                if TotalImages:
                                    Progress = (CurrentCount / TotalImages) * 100
                                    print(f"\r⟳ Progression: {CurrentCount}/{TotalImages} images ({Progress:.1f}%)", end='', flush=True)

                                    # Log toutes les 10 images ou toutes les 5 secondes
                                    CurrentTime = time.time()
                                    if CurrentCount % 10 == 0 or (CurrentTime - LastLogTime) >= 5:
                                        print()  # Nouvelle ligne
                                        self.Logger.info(f"⟳ Progression: {CurrentCount}/{TotalImages} images ({Progress:.1f}%)")
                                        LastLogTime = CurrentTime
                                else:
                                    print(f"\r⟳ Progression: {CurrentCount} images", end='', flush=True)

                                # Appelle le callback
                                if ProgressCallback:
                                    ProgressCallback(CurrentCount, TotalImages or CurrentCount)

                        # Vérifie toutes les 0.5 secondes
                        time.sleep(0.5)
                    except Exception as e:
                        self.Logger.debug(f"Erreur monitoring: {e}")
                        break

            # Démarre le thread de surveillance
            MonitorThread = threading.Thread(target=MonitorOutputDirectory, daemon=True)
            MonitorThread.start()

            # Exécute Real-ESRGAN et capture la sortie
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

            # Lit la sortie ligne par ligne (pour capturer les erreurs et infos GPU)
            for Line in iter(Process.stdout.readline, ''):
                if not Line:
                    break

                Line = Line.strip()
                AllOutput.append(Line)

                if not Line:
                    continue

                # Affiche les 5 premières lignes (infos GPU)
                if FirstLines < 5:
                    self.Logger.info(f"[Real-ESRGAN] {Line}")
                    FirstLines += 1

            # Attend la fin du processus
            ReturnCode = Process.wait()

            # Arrête le thread de surveillance
            StopMonitoring.set()
            MonitorThread.join(timeout=2)

            # Nouvelle ligne finale
            print()

            # Récupère le compte final
            CurrentImage = MonitoredCount[0]

            if ReturnCode == 0:
                # Log final avec le nombre d'images traitées
                if TotalImages:
                    self.Logger.info(f"✓ Real-ESRGAN terminé: {CurrentImage}/{TotalImages} images upscalées")
                else:
                    self.Logger.info(f"✓ Real-ESRGAN terminé: {CurrentImage} images upscalées")
                return True, ""
            else:
                # Affiche les dernières lignes de sortie en cas d'erreur
                ErrorMsg = '\n'.join(AllOutput[-10:]) if AllOutput else "Erreur inconnue"
                self.Logger.error(f"Erreur Real-ESRGAN (code {ReturnCode}): {ErrorMsg}")
                return False, ErrorMsg

        except Exception as e:
            ErrorMsg = f"Erreur lors de l'upscaling du dossier: {e}"
            self.Logger.error(ErrorMsg)
            return False, ErrorMsg

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
