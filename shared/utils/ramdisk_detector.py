"""
Module de détection et gestion des RAM disks
Supporte Linux (tmpfs natif) et Windows (ImDisk)
"""

import os
import platform
import shutil
from dataclasses import dataclass
from typing import Optional, List

from shared.utils.logger import GetModuleLogger

# Dépendance optionnelle pour Windows (ImDisk)
try:
    from ramdisk import create_hd, remove_hd, list_hds
    IMDISK_AVAILABLE = True
except ImportError:
    IMDISK_AVAILABLE = False


@dataclass
class RamDiskInfo:
    """Informations sur un RAM disk détecté"""
    path: str
    total_mb: int
    available_mb: int
    is_writable: bool
    source: str  # "shm", "run_user", "imdisk", "manual"


@dataclass
class RamDiskValidationResult:
    """Résultat de validation d'un chemin RAM disk"""
    is_valid: bool
    error_message: str = ""
    is_ramdisk: bool = False
    available_mb: int = 0


class RamDiskDetector:
    """Détection multi-plateforme des RAM disks"""

    LINUX_SHM_PATH = "/dev/shm"
    LINUX_RUN_USER_PATH = "/run/user/{uid}"
    MIN_REQUIRED_SPACE_MB = 500

    def __init__(self):
        self.Logger = GetModuleLogger("RamDiskDetector")

    @staticmethod
    def DetectAvailable() -> List[RamDiskInfo]:
        """
        Détecte les RAM disks disponibles sur le système

        Returns:
            Liste de RamDiskInfo pour chaque RAM disk trouvé
        """
        RamDisks = []
        System = platform.system()

        if System == "Linux":
            RamDisks.extend(RamDiskDetector._DetectLinuxRamDisks())
        elif System == "Windows":
            RamDisks.extend(RamDiskDetector._DetectWindowsRamDisks())

        return RamDisks

    @staticmethod
    def _DetectLinuxRamDisks() -> List[RamDiskInfo]:
        """Détecte les RAM disks sur Linux (tmpfs)"""
        RamDisks = []

        # Vérifie /dev/shm
        ShmPath = RamDiskDetector.LINUX_SHM_PATH
        if os.path.exists(ShmPath) and RamDiskDetector._IsTmpfs(ShmPath):
            Info = RamDiskDetector._GetPathInfo(ShmPath, "shm")
            if Info:
                RamDisks.append(Info)

        # Vérifie /run/user/{uid}
        try:
            Uid = os.getuid()
            RunUserPath = f"/run/user/{Uid}"
            if os.path.exists(RunUserPath) and RamDiskDetector._IsTmpfs(RunUserPath):
                Info = RamDiskDetector._GetPathInfo(RunUserPath, "run_user")
                if Info:
                    RamDisks.append(Info)
        except (AttributeError, OSError):
            pass  # os.getuid() n'existe pas sur Windows

        return RamDisks

    @staticmethod
    def _DetectWindowsRamDisks() -> List[RamDiskInfo]:
        """Détecte les RAM disks sur Windows (ImDisk)"""
        RamDisks = []

        if not IMDISK_AVAILABLE:
            return RamDisks

        try:
            # Liste les disques ImDisk existants
            ExistingDisks = list_hds()
            for DiskInfo in ExistingDisks:
                DriveLetter = DiskInfo.get("drive_letter", "")
                if DriveLetter:
                    Path = f"{DriveLetter}:\\"
                    Info = RamDiskDetector._GetPathInfo(Path, "imdisk")
                    if Info:
                        RamDisks.append(Info)
        except Exception:
            pass

        return RamDisks

    @staticmethod
    def _IsTmpfs(Path: str) -> bool:
        """
        Vérifie si un chemin est sur un tmpfs (Linux)

        Args:
            Path: Chemin à vérifier

        Returns:
            True si c'est un tmpfs
        """
        try:
            with open("/proc/mounts", "r") as f:
                for Line in f:
                    Parts = Line.split()
                    if len(Parts) >= 3:
                        MountPoint = Parts[1]
                        FsType = Parts[2]
                        if Path.startswith(MountPoint) and FsType in ("tmpfs", "ramfs"):
                            return True
        except (FileNotFoundError, PermissionError):
            pass

        return False

    @staticmethod
    def _GetPathInfo(Path: str, Source: str) -> Optional[RamDiskInfo]:
        """
        Récupère les informations d'espace pour un chemin

        Args:
            Path: Chemin du RAM disk
            Source: Source de détection ("shm", "run_user", "imdisk", "manual")

        Returns:
            RamDiskInfo ou None si erreur
        """
        try:
            Usage = shutil.disk_usage(Path)
            TotalMb = Usage.total // (1024 * 1024)
            AvailableMb = Usage.free // (1024 * 1024)

            # Vérifie si on peut écrire
            IsWritable = os.access(Path, os.W_OK)

            return RamDiskInfo(
                path=Path,
                total_mb=TotalMb,
                available_mb=AvailableMb,
                is_writable=IsWritable,
                source=Source
            )
        except Exception:
            return None

    @staticmethod
    def GetBestRamDisk(MinSpaceMb: int = 500) -> Optional[RamDiskInfo]:
        """
        Retourne le meilleur RAM disk disponible

        Args:
            MinSpaceMb: Espace minimum requis en MB

        Returns:
            RamDiskInfo du meilleur RAM disk ou None
        """
        RamDisks = RamDiskDetector.DetectAvailable()

        # Filtre par espace minimum et permissions d'écriture
        ValidDisks = [
            d for d in RamDisks
            if d.available_mb >= MinSpaceMb and d.is_writable
        ]

        if not ValidDisks:
            return None

        # Trie par espace disponible (décroissant)
        ValidDisks.sort(key=lambda d: d.available_mb, reverse=True)

        return ValidDisks[0]

    @staticmethod
    def ValidateRamDiskPath(Path: str) -> RamDiskValidationResult:
        """
        Valide un chemin comme RAM disk potentiel

        Args:
            Path: Chemin à valider

        Returns:
            RamDiskValidationResult
        """
        if not Path:
            return RamDiskValidationResult(
                is_valid=False,
                error_message="Chemin vide"
            )

        if not os.path.exists(Path):
            return RamDiskValidationResult(
                is_valid=False,
                error_message=f"Le chemin n'existe pas: {Path}"
            )

        if not os.path.isdir(Path):
            return RamDiskValidationResult(
                is_valid=False,
                error_message=f"Le chemin n'est pas un répertoire: {Path}"
            )

        if not os.access(Path, os.W_OK):
            return RamDiskValidationResult(
                is_valid=False,
                error_message=f"Permissions d'écriture refusées: {Path}"
            )

        # Vérifie si c'est un vrai RAM disk (tmpfs)
        IsRamDisk = False
        System = platform.system()

        if System == "Linux":
            IsRamDisk = RamDiskDetector._IsTmpfs(Path)
        elif System == "Windows":
            # Sur Windows, on considère que c'est un RAM disk si spécifié manuellement
            IsRamDisk = True

        # Récupère l'espace disponible
        try:
            Usage = shutil.disk_usage(Path)
            AvailableMb = Usage.free // (1024 * 1024)
        except Exception:
            AvailableMb = 0

        return RamDiskValidationResult(
            is_valid=True,
            is_ramdisk=IsRamDisk,
            available_mb=AvailableMb
        )

    @staticmethod
    def GetAvailableSpace(Path: str) -> int:
        """
        Retourne l'espace disponible en MB pour un chemin

        Args:
            Path: Chemin à vérifier

        Returns:
            Espace disponible en MB ou 0 si erreur
        """
        try:
            Usage = shutil.disk_usage(Path)
            return Usage.free // (1024 * 1024)
        except Exception:
            return 0

    @staticmethod
    def IsRamDisk(Path: str) -> bool:
        """
        Vérifie si un chemin est sur un RAM disk

        Args:
            Path: Chemin à vérifier

        Returns:
            True si c'est un RAM disk
        """
        System = platform.system()

        if System == "Linux":
            return RamDiskDetector._IsTmpfs(Path)
        elif System == "Windows":
            # Sur Windows, vérifie si c'est un disque ImDisk
            if IMDISK_AVAILABLE:
                try:
                    ExistingDisks = list_hds()
                    for DiskInfo in ExistingDisks:
                        DriveLetter = DiskInfo.get("drive_letter", "")
                        if Path.upper().startswith(f"{DriveLetter}:".upper()):
                            return True
                except Exception:
                    pass
            return False

        return False


class WindowsRamDiskManager:
    """Gestion du RAM disk Windows via ImDisk"""

    DEFAULT_DRIVE_LETTER = "R"
    DEFAULT_SIZE_MB = 2048

    def __init__(self):
        self.Logger = GetModuleLogger("WindowsRamDiskManager")
        self.CreatedDriveLetter = None

    @staticmethod
    def IsImDiskInstalled() -> bool:
        """
        Vérifie si ImDisk est installé et accessible

        Returns:
            True si ImDisk est disponible
        """
        if not IMDISK_AVAILABLE:
            return False

        # Vérifie que la bibliothèque fonctionne
        try:
            # Tente de lister les disques (test basique)
            list_hds()
            return True
        except Exception:
            return False

    @staticmethod
    def IsImDiskLibraryAvailable() -> bool:
        """
        Vérifie si la bibliothèque ramdisk est installée

        Returns:
            True si la bibliothèque est disponible
        """
        return IMDISK_AVAILABLE

    def CreateRamDisk(
        self,
        SizeMb: int = DEFAULT_SIZE_MB,
        DriveLetter: str = DEFAULT_DRIVE_LETTER,
        FileSystem: str = "ntfs"
    ) -> Optional[str]:
        """
        Crée un RAM disk via ImDisk

        Args:
            SizeMb: Taille en MB
            DriveLetter: Lettre du lecteur (sans ':')
            FileSystem: Système de fichiers ("ntfs" ou "fat32")

        Returns:
            Chemin du RAM disk (ex: "R:\\") ou None si erreur
        """
        if not IMDISK_AVAILABLE:
            self.Logger.error("Bibliothèque ramdisk non disponible")
            return None

        if not WindowsRamDiskManager.IsImDiskInstalled():
            self.Logger.error("ImDisk n'est pas installé sur ce système")
            return None

        try:
            self.Logger.info(f"Initialisation du RAM disk {DriveLetter}: ({SizeMb} MB, {FileSystem})")

            # Supprime d'abord si existe déjà (cleanup)
            self.RemoveRamDisk(DriveLetter)

            # Crée le nouveau RAM disk SANS formatage automatique
            # (le paramètre fs de create_hd ne fonctionne pas toujours correctement)
            self.Logger.info(f"Création du disque virtuel {DriveLetter}:...")
            create_hd(
                size_in_megabyte=SizeMb,
                drive_letter=DriveLetter
            )

            self.CreatedDriveLetter = DriveLetter
            Path = f"{DriveLetter}:\\"

            self.Logger.info(f"Disque virtuel {DriveLetter}: créé, formatage en cours...")

            # Formate toujours le disque manuellement pour garantir qu'il soit utilisable
            if not self._FormatDrive(DriveLetter, FileSystem):
                self.Logger.error("Échec du formatage")
                self.RemoveRamDisk(DriveLetter)
                return None

            # Vérifie que le disque est maintenant accessible
            import time
            time.sleep(1)

            try:
                # Tente de lister le contenu
                os.listdir(Path)
                self.Logger.info(f"RAM disk {Path} formaté et accessible")
            except (OSError, PermissionError) as e:
                self.Logger.error(f"Le disque {Path} n'est toujours pas accessible après formatage: {e}")
                self.RemoveRamDisk(DriveLetter)
                return None

            self.Logger.info(f"RAM disk créé avec succès: {Path}")
            return Path

        except Exception as e:
            self.Logger.error(f"Erreur lors de la création du RAM disk: {e}")
            return None

    def _FormatDrive(self, DriveLetter: str, FileSystem: str) -> bool:
        """
        Formate manuellement un lecteur avec le système de fichiers spécifié

        Args:
            DriveLetter: Lettre du lecteur (sans ':')
            FileSystem: "ntfs" ou "fat32"

        Returns:
            True si succès
        """
        import subprocess
        import time

        try:
            # Conversion du système de fichiers
            FsType = "NTFS" if FileSystem.lower() == "ntfs" else "FAT32"

            # Attend que le disque soit créé par ImDisk
            self.Logger.info("Attente de la création du disque par ImDisk...")

            # Vérifie via ImDisk que le disque existe (même non formaté)
            MaxRetries = 10
            DiskExists = False

            for i in range(MaxRetries):
                try:
                    ExistingDisks = list_hds()
                    for DiskInfo in ExistingDisks:
                        if DiskInfo.get("drive_letter", "").upper() == DriveLetter.upper():
                            self.Logger.debug(f"Disque {DriveLetter}: détecté par ImDisk après {i+1} tentatives")
                            DiskExists = True
                            break
                    if DiskExists:
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            if not DiskExists:
                self.Logger.error(f"Le disque {DriveLetter}: n'est pas créé par ImDisk après {MaxRetries/2} secondes")
                return False

            # Attend que Windows monte le disque (délai fixe)
            self.Logger.debug("Attente du montage par Windows...")
            time.sleep(2)

            # Méthode directe : format.com avec /FS et /Q (formatage rapide)
            self.Logger.info(f"Formatage de {DriveLetter}: en {FsType} (rapide)...")

            # Utilise format avec echo Y pour auto-confirmer
            Command = f'format {DriveLetter}: /FS:{FsType} /Q /V:RAMDISK /Y'

            self.Logger.debug(f"Commande: {Command}")

            Result = subprocess.run(
                Command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )

            self.Logger.debug(f"Commande 1 - returncode: {Result.returncode}")
            self.Logger.debug(f"Commande 1 - stdout: {Result.stdout}")
            self.Logger.debug(f"Commande 1 - stderr: {Result.stderr}")

            if Result.returncode == 0:
                self.Logger.info(f"Formatage réussi: {DriveLetter}: ({FsType})")
                time.sleep(1)  # Attend que le formatage soit finalisé
                return True

            # Si échec, essaie sans /Y (avec echo Y à la place)
            self.Logger.warning("Tentative avec echo Y...")
            Command2 = f'echo Y|format {DriveLetter}: /FS:{FsType} /Q /V:RAMDISK'
            self.Logger.debug(f"Commande 2: {Command2}")

            Result2 = subprocess.run(
                Command2,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )

            self.Logger.debug(f"Commande 2 - returncode: {Result2.returncode}")
            self.Logger.debug(f"Commande 2 - stdout: {Result2.stdout}")
            self.Logger.debug(f"Commande 2 - stderr: {Result2.stderr}")

            if Result2.returncode == 0:
                self.Logger.info(f"Formatage réussi: {DriveLetter}:")
                time.sleep(1)
                return True
            else:
                self.Logger.error(f"Échec du formatage après 2 tentatives")
                return False

        except subprocess.TimeoutExpired:
            self.Logger.error("Timeout lors du formatage (> 60s)")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors du formatage: {e}")
            import traceback
            self.Logger.debug(traceback.format_exc())
            return False

    def RemoveRamDisk(self, DriveLetter: str = None) -> bool:
        """
        Supprime un RAM disk

        Args:
            DriveLetter: Lettre du lecteur (si None, utilise le dernier créé)

        Returns:
            True si succès
        """
        if not IMDISK_AVAILABLE:
            return False

        if DriveLetter is None:
            DriveLetter = self.CreatedDriveLetter

        if not DriveLetter:
            return False

        try:
            self.Logger.info(f"Suppression du RAM disk {DriveLetter}:")

            remove_hd(drive_letter=DriveLetter, force=True)

            if self.CreatedDriveLetter == DriveLetter:
                self.CreatedDriveLetter = None

            self.Logger.info(f"RAM disk {DriveLetter}: supprimé avec succès")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la suppression du RAM disk: {e}")
            return False

    @staticmethod
    def GetExistingRamDisk(DriveLetter: str = None) -> Optional[RamDiskInfo]:
        """
        Récupère les informations d'un RAM disk existant

        Args:
            DriveLetter: Lettre spécifique ou None pour le premier trouvé

        Returns:
            RamDiskInfo ou None
        """
        if not IMDISK_AVAILABLE:
            return None

        try:
            ExistingDisks = list_hds()

            for DiskInfo in ExistingDisks:
                CurrentLetter = DiskInfo.get("drive_letter", "")

                if DriveLetter and CurrentLetter.upper() != DriveLetter.upper():
                    continue

                if CurrentLetter:
                    Path = f"{CurrentLetter}:\\"
                    return RamDiskDetector._GetPathInfo(Path, "imdisk")

        except Exception:
            pass

        return None

    @staticmethod
    def GetAvailableDriveLetters() -> List[str]:
        """
        Retourne les lettres de lecteur disponibles

        Returns:
            Liste de lettres disponibles (ex: ["R", "S", "T", ...])
        """
        import string

        # Lettres candidates (R-Z, évite les lettres communes)
        Candidates = list("RSTUVWXYZ")
        Available = []

        for Letter in Candidates:
            Path = f"{Letter}:\\"
            if not os.path.exists(Path):
                Available.append(Letter)

        return Available
