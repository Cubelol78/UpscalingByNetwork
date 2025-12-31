"""
Détecteur de matériel pour l'optimisation de Real-ESRGAN
Détecte CPU, RAM et GPU Vulkan pour configurer les performances optimales
"""

import os
import re
import subprocess
import platform
from typing import List, Dict, Optional
from pathlib import Path

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from shared.utils.logger import GetModuleLogger


class HardwareDetector:
    """Détecteur de matériel pour optimisation Real-ESRGAN"""

    def __init__(self, ProjectRoot: Optional[str] = None):
        """
        Initialise le détecteur de matériel

        Args:
            ProjectRoot: Racine du projet (pour trouver Real-ESRGAN)
        """
        self.Logger = GetModuleLogger("HardwareDetector")
        self.ProjectRoot = ProjectRoot or self._DetectProjectRoot()
        self.CachedHardware = None

    def _DetectProjectRoot(self) -> str:
        """Détecte la racine du projet"""
        CurrentPath = Path(__file__).resolve()
        # Remonte de client/utils vers la racine
        return str(CurrentPath.parent.parent.parent)

    def DetectAll(self, ForceRefresh: bool = False) -> Dict:
        """
        Détecte tout le matériel

        Args:
            ForceRefresh: Force la re-détection même si en cache

        Returns:
            Dictionnaire avec les informations matérielles
        """
        if self.CachedHardware and not ForceRefresh:
            return self.CachedHardware

        self.Logger.info("Détection du matériel...")

        Hardware = {
            "cpu": self.DetectCpu(),
            "ram": self.DetectRam(),
            "gpu": self.DetectGpus()
        }

        self.CachedHardware = Hardware
        return Hardware

    def DetectCpu(self) -> Dict:
        """
        Détecte les informations du CPU

        Returns:
            Dictionnaire avec les infos CPU
        """
        try:
            CpuInfo = {
                "physical_cores": 1,
                "logical_cores": 1,
                "name": "Unknown CPU",
                "architecture": platform.machine()
            }

            if PSUTIL_AVAILABLE:
                CpuInfo["physical_cores"] = psutil.cpu_count(logical=False) or 1
                CpuInfo["logical_cores"] = psutil.cpu_count(logical=True) or 1

                # Essaie d'obtenir la fréquence
                try:
                    Freq = psutil.cpu_freq()
                    if Freq:
                        CpuInfo["frequency_mhz"] = Freq.current
                except Exception:
                    pass
            else:
                # Fallback sans psutil
                CpuInfo["logical_cores"] = os.cpu_count() or 1
                CpuInfo["physical_cores"] = CpuInfo["logical_cores"]

            # Essaie d'obtenir le nom du CPU
            CpuInfo["name"] = self._GetCpuName()

            self.Logger.info(f"CPU détecté: {CpuInfo['name']} ({CpuInfo['physical_cores']} coeurs)")
            return CpuInfo

        except Exception as e:
            self.Logger.error(f"Erreur lors de la détection CPU: {e}")
            return {
                "physical_cores": 1,
                "logical_cores": os.cpu_count() or 1,
                "name": "Unknown CPU",
                "architecture": platform.machine()
            }

    def _GetCpuName(self) -> str:
        """Récupère le nom du CPU"""
        try:
            System = platform.system()

            if System == "Linux":
                # Lecture de /proc/cpuinfo
                with open("/proc/cpuinfo", "r") as f:
                    for Line in f:
                        if "model name" in Line:
                            return Line.split(":")[1].strip()

            elif System == "Windows":
                # Utilise wmic
                Result = subprocess.run(
                    ["wmic", "cpu", "get", "name"],
                    capture_output=True,
                    text=True
                )
                if Result.returncode == 0:
                    Lines = Result.stdout.strip().split("\n")
                    if len(Lines) > 1:
                        return Lines[1].strip()

            elif System == "Darwin":
                # macOS
                Result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True
                )
                if Result.returncode == 0:
                    return Result.stdout.strip()

        except Exception:
            pass

        return "Unknown CPU"

    def DetectRam(self) -> Dict:
        """
        Détecte les informations de la RAM

        Returns:
            Dictionnaire avec les infos RAM
        """
        try:
            RamInfo = {
                "total_bytes": 0,
                "total_gb": 0,
                "available_bytes": 0,
                "available_gb": 0,
                "percent_used": 0
            }

            if PSUTIL_AVAILABLE:
                Memory = psutil.virtual_memory()
                RamInfo["total_bytes"] = Memory.total
                RamInfo["total_gb"] = round(Memory.total / (1024 ** 3), 1)
                RamInfo["available_bytes"] = Memory.available
                RamInfo["available_gb"] = round(Memory.available / (1024 ** 3), 1)
                RamInfo["percent_used"] = Memory.percent
            else:
                # Fallback: essaie de lire depuis /proc/meminfo sur Linux
                RamInfo = self._GetRamFallback()

            self.Logger.info(f"RAM détectée: {RamInfo['total_gb']} GB ({RamInfo['available_gb']} GB disponible)")
            return RamInfo

        except Exception as e:
            self.Logger.error(f"Erreur lors de la détection RAM: {e}")
            return {
                "total_bytes": 0,
                "total_gb": 0,
                "available_bytes": 0,
                "available_gb": 0,
                "percent_used": 0
            }

    def _GetRamFallback(self) -> Dict:
        """Fallback pour la détection RAM sans psutil"""
        RamInfo = {
            "total_bytes": 0,
            "total_gb": 0,
            "available_bytes": 0,
            "available_gb": 0,
            "percent_used": 0
        }

        try:
            System = platform.system()

            if System == "Linux":
                with open("/proc/meminfo", "r") as f:
                    Content = f.read()

                # Parse MemTotal et MemAvailable
                for Line in Content.split("\n"):
                    if Line.startswith("MemTotal:"):
                        Kb = int(Line.split()[1])
                        RamInfo["total_bytes"] = Kb * 1024
                        RamInfo["total_gb"] = round(Kb / (1024 ** 2), 1)
                    elif Line.startswith("MemAvailable:"):
                        Kb = int(Line.split()[1])
                        RamInfo["available_bytes"] = Kb * 1024
                        RamInfo["available_gb"] = round(Kb / (1024 ** 2), 1)

                if RamInfo["total_bytes"] > 0:
                    Used = RamInfo["total_bytes"] - RamInfo["available_bytes"]
                    RamInfo["percent_used"] = round((Used / RamInfo["total_bytes"]) * 100, 1)

            elif System == "Windows":
                import ctypes
                Kernel32 = ctypes.windll.kernel32

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                MemoryStatus = MEMORYSTATUSEX()
                MemoryStatus.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                Kernel32.GlobalMemoryStatusEx(ctypes.byref(MemoryStatus))

                RamInfo["total_bytes"] = MemoryStatus.ullTotalPhys
                RamInfo["total_gb"] = round(MemoryStatus.ullTotalPhys / (1024 ** 3), 1)
                RamInfo["available_bytes"] = MemoryStatus.ullAvailPhys
                RamInfo["available_gb"] = round(MemoryStatus.ullAvailPhys / (1024 ** 3), 1)
                RamInfo["percent_used"] = MemoryStatus.dwMemoryLoad

        except Exception as e:
            self.Logger.error(f"Erreur fallback RAM: {e}")

        return RamInfo

    def DetectGpus(self) -> List[Dict]:
        """
        Détecte les GPU Vulkan disponibles via Real-ESRGAN

        Returns:
            Liste des GPU détectés avec leurs informations
        """
        try:
            Gpus = []

            # Méthode 1: Parser la sortie de Real-ESRGAN
            RealEsrganGpus = self._DetectGpusViaRealEsrgan()
            if RealEsrganGpus:
                Gpus = RealEsrganGpus

            # Méthode 2: Fallback vulkaninfo si disponible
            if not Gpus:
                VulkanGpus = self._DetectGpusViaVulkaninfo()
                if VulkanGpus:
                    Gpus = VulkanGpus

            # Méthode 3: Fallback nvidia-smi pour NVIDIA
            if not Gpus:
                NvidiaGpus = self._DetectGpusViaNvidiaSmi()
                if NvidiaGpus:
                    Gpus = NvidiaGpus

            # Enrichissement: Pour les GPU NVIDIA, nvidia-smi donne la vraie VRAM
            # On corrige les valeurs estimées par les vraies valeurs
            if Gpus:
                Gpus = self._EnrichWithNvidiaSmiVram(Gpus)

            if Gpus:
                for Gpu in Gpus:
                    VramStr = f" ({Gpu.get('vram_mb', '?')} MB)" if Gpu.get('vram_mb') else ""
                    self.Logger.info(f"GPU {Gpu['id']}: {Gpu['name']}{VramStr}")
            else:
                self.Logger.warning("Aucun GPU Vulkan détecté, Real-ESRGAN utilisera le CPU")
                Gpus = [{"id": -1, "name": "CPU (pas de GPU)", "vram_mb": 0}]

            return Gpus

        except Exception as e:
            self.Logger.error(f"Erreur lors de la détection GPU: {e}")
            return [{"id": -1, "name": "CPU (erreur détection)", "vram_mb": 0}]

    def _DetectGpusViaRealEsrgan(self) -> List[Dict]:
        """Détecte les GPU via Real-ESRGAN lui-même"""
        try:
            # Trouve l'exécutable Real-ESRGAN
            System = platform.system()
            if System == "Linux":
                ExecPath = os.path.join(
                    self.ProjectRoot,
                    "realesrgan-ncnn-vulkan-20220424-ubuntu",
                    "realesrgan-ncnn-vulkan"
                )
            elif System == "Windows":
                ExecPath = os.path.join(
                    self.ProjectRoot,
                    "realesrgan-ncnn-vulkan-20220424-windows",
                    "realesrgan-ncnn-vulkan.exe"
                )
            else:
                return []

            if not os.path.exists(ExecPath):
                return []

            # Exécute avec -g -1 pour forcer l'affichage des GPU disponibles
            Result = subprocess.run(
                [ExecPath, "-i", "nonexistent.png", "-o", "out.png", "-g", "-1"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=os.path.dirname(ExecPath)
            )

            # Parse la sortie stderr pour trouver les GPU
            Output = Result.stderr + Result.stdout
            Gpus = self._ParseGpuList(Output)

            return Gpus

        except subprocess.TimeoutExpired:
            self.Logger.warning("Timeout lors de la détection GPU via Real-ESRGAN")
            return []
        except Exception as e:
            self.Logger.debug(f"Détection GPU via Real-ESRGAN échouée: {e}")
            return []

    def _ParseGpuList(self, Output: str) -> List[Dict]:
        """Parse la sortie de Real-ESRGAN pour extraire la liste des GPU"""
        Gpus = []
        SeenIds = set()  # Pour éviter les doublons

        # Format Real-ESRGAN ncnn-vulkan:
        # [0 NVIDIA GeForce GTX 970]  queueC=0[16]  queueG=0[16]  queueT=1[2]
        # [1 Intel(R) HD Graphics 530]  queueC=0[1]  queueG=0[1]  queueT=0[1]
        #
        # Le pattern doit matcher [ID NOM_GPU] au début de ligne
        # et ignorer les [N] dans queueC=0[16] etc.

        Lines = Output.split('\n')
        for Line in Lines:
            Line = Line.strip()
            if not Line:
                continue

            # Pattern principal: [0 GPU Name] au début de ligne
            Match = re.match(r'^\[(\d+)\s+([^\]]+)\]', Line)
            if Match:
                GpuId = int(Match.group(1))
                GpuName = Match.group(2).strip()

                # Évite les doublons
                if GpuId in SeenIds:
                    continue

                # Vérifie que c'est un nom de GPU valide (contient des mots clés GPU)
                GpuKeywords = ['nvidia', 'geforce', 'rtx', 'gtx', 'quadro',
                              'amd', 'radeon', 'intel', 'graphics', 'gpu', 'hd']
                NameLower = GpuName.lower()
                if any(kw in NameLower for kw in GpuKeywords):
                    SeenIds.add(GpuId)
                    Gpus.append({
                        "id": GpuId,
                        "name": GpuName,
                        "vram_mb": self._EstimateVram(GpuName)
                    })

        return Gpus

    def _DetectGpusViaVulkaninfo(self) -> List[Dict]:
        """Détecte les GPU via vulkaninfo"""
        try:
            Result = subprocess.run(
                ["vulkaninfo", "--summary"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if Result.returncode != 0:
                return []

            Gpus = []
            GpuIndex = 0

            # Parse la sortie de vulkaninfo
            for Line in Result.stdout.split("\n"):
                if "deviceName" in Line:
                    GpuName = Line.split("=")[1].strip() if "=" in Line else Line.split(":")[1].strip()
                    Gpus.append({
                        "id": GpuIndex,
                        "name": GpuName,
                        "vram_mb": self._EstimateVram(GpuName)
                    })
                    GpuIndex += 1

            return Gpus

        except FileNotFoundError:
            return []
        except Exception as e:
            self.Logger.debug(f"Détection GPU via vulkaninfo échouée: {e}")
            return []

    def _DetectGpusViaNvidiaSmi(self) -> List[Dict]:
        """Détecte les GPU NVIDIA via nvidia-smi"""
        try:
            Result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if Result.returncode != 0:
                return []

            Gpus = []
            for Line in Result.stdout.strip().split("\n"):
                Parts = Line.split(",")
                if len(Parts) >= 2:
                    GpuId = int(Parts[0].strip())
                    GpuName = Parts[1].strip()
                    VramMb = int(Parts[2].strip()) if len(Parts) > 2 else self._EstimateVram(GpuName)
                    Gpus.append({
                        "id": GpuId,
                        "name": GpuName,
                        "vram_mb": VramMb
                    })

            return Gpus

        except FileNotFoundError:
            return []
        except Exception as e:
            self.Logger.debug(f"Détection GPU via nvidia-smi échouée: {e}")
            return []

    def _EnrichWithNvidiaSmiVram(self, Gpus: List[Dict]) -> List[Dict]:
        """
        Enrichit la liste des GPU avec les vraies valeurs VRAM de nvidia-smi.
        Pour les GPU NVIDIA, nvidia-smi retourne la vraie VRAM au lieu d'une estimation.

        Args:
            Gpus: Liste des GPU détectés

        Returns:
            Liste enrichie avec les vraies valeurs VRAM pour les GPU NVIDIA
        """
        try:
            Result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if Result.returncode != 0:
                return Gpus

            # Parse les données nvidia-smi
            NvidiaData = {}
            for Line in Result.stdout.strip().split("\n"):
                Parts = Line.split(",")
                if len(Parts) >= 3:
                    GpuName = Parts[1].strip().lower()
                    VramMb = int(Parts[2].strip())
                    NvidiaData[GpuName] = VramMb

            # Enrichit les GPU détectés
            for Gpu in Gpus:
                GpuNameLower = Gpu.get("name", "").lower()
                # Cherche une correspondance dans les données nvidia-smi
                for NvidiaName, VramMb in NvidiaData.items():
                    # Correspondance partielle (le nom peut varier légèrement)
                    if NvidiaName in GpuNameLower or GpuNameLower in NvidiaName:
                        OldVram = Gpu.get("vram_mb", 0)
                        if VramMb != OldVram:
                            self.Logger.info(f"VRAM corrigée pour {Gpu['name']}: {OldVram} MB -> {VramMb} MB")
                        Gpu["vram_mb"] = VramMb
                        break
                    # Correspondance par mots clés (RTX 4060 Ti, etc.)
                    NvidiaWords = set(NvidiaName.replace("-", " ").split())
                    GpuWords = set(GpuNameLower.replace("-", " ").split())
                    CommonWords = NvidiaWords & GpuWords
                    # Si on a au moins 3 mots en commun (ex: "geforce", "rtx", "4060")
                    if len(CommonWords) >= 3:
                        OldVram = Gpu.get("vram_mb", 0)
                        if VramMb != OldVram:
                            self.Logger.info(f"VRAM corrigée pour {Gpu['name']}: {OldVram} MB -> {VramMb} MB")
                        Gpu["vram_mb"] = VramMb
                        break

            return Gpus

        except FileNotFoundError:
            # nvidia-smi non disponible (pas de driver NVIDIA ou GPU non-NVIDIA)
            return Gpus
        except Exception as e:
            self.Logger.debug(f"Enrichissement VRAM via nvidia-smi échoué: {e}")
            return Gpus

    def _EstimateVram(self, GpuName: str) -> int:
        """
        Estime la VRAM basée sur le nom du GPU

        Args:
            GpuName: Nom du GPU

        Returns:
            VRAM estimée en MB
        """
        GpuNameLower = GpuName.lower()

        # NVIDIA RTX 40 series
        if "4090" in GpuNameLower:
            return 24576
        elif "4080" in GpuNameLower:
            return 16384
        elif "4070 ti" in GpuNameLower or "4070ti" in GpuNameLower:
            return 12288
        elif "4070" in GpuNameLower:
            return 12288
        # RTX 4060 Ti 16GB (doit être vérifié AVANT la version standard)
        elif ("4060 ti" in GpuNameLower or "4060ti" in GpuNameLower) and ("16g" in GpuNameLower or "16 g" in GpuNameLower):
            return 16384
        elif "4060 ti" in GpuNameLower or "4060ti" in GpuNameLower:
            return 8192
        elif "4060" in GpuNameLower:
            return 8192
        elif "4050" in GpuNameLower:
            return 6144  # Laptop

        # NVIDIA RTX 30 series
        elif "3090" in GpuNameLower:
            return 24576
        elif "3080 ti" in GpuNameLower:
            return 12288
        elif "3080" in GpuNameLower:
            return 10240
        elif "3070 ti" in GpuNameLower:
            return 8192
        elif "3070" in GpuNameLower:
            return 8192
        elif "3060 ti" in GpuNameLower:
            return 8192
        elif "3060" in GpuNameLower:
            return 12288
        elif "3050 ti" in GpuNameLower:
            return 4096
        elif "3050" in GpuNameLower:
            return 4096  # Desktop 8GB ou Laptop 4GB

        # NVIDIA RTX 20 series
        elif "2080 ti" in GpuNameLower:
            return 11264
        elif "2080" in GpuNameLower:
            return 8192
        elif "2070" in GpuNameLower:
            return 8192
        elif "2060" in GpuNameLower:
            return 6144

        # NVIDIA GTX 16 series
        elif "1660" in GpuNameLower:
            return 6144
        elif "1650" in GpuNameLower:
            return 4096

        # NVIDIA GTX 10 series
        elif "1080 ti" in GpuNameLower:
            return 11264
        elif "1080" in GpuNameLower:
            return 8192
        elif "1070 ti" in GpuNameLower:
            return 8192
        elif "1070" in GpuNameLower:
            return 8192
        elif "1060" in GpuNameLower:
            return 6144
        elif "1050 ti" in GpuNameLower:
            return 4096
        elif "1050" in GpuNameLower:
            return 2048  # Version 2GB ou 4GB

        # NVIDIA GTX 9 series (Maxwell)
        elif "980 ti" in GpuNameLower:
            return 6144
        elif "980" in GpuNameLower:
            return 4096
        elif "970" in GpuNameLower:
            return 4096  # 3.5GB effectifs mais 4GB affichés
        elif "960" in GpuNameLower:
            return 4096  # Version 2GB ou 4GB
        elif "950" in GpuNameLower:
            return 2048

        # NVIDIA GTX 7 series (Kepler)
        elif "780 ti" in GpuNameLower:
            return 3072
        elif "780" in GpuNameLower:
            return 3072
        elif "770" in GpuNameLower:
            return 2048  # Version 2GB ou 4GB
        elif "760" in GpuNameLower:
            return 2048
        elif "750 ti" in GpuNameLower:
            return 2048
        elif "750" in GpuNameLower:
            return 1024

        # NVIDIA Titan series
        elif "titan rtx" in GpuNameLower:
            return 24576
        elif "titan v" in GpuNameLower:
            return 12288
        elif "titan xp" in GpuNameLower or "titan x pascal" in GpuNameLower:
            return 12288
        elif "titan x" in GpuNameLower:
            return 12288

        # AMD RX 7000 series
        elif "7900 xtx" in GpuNameLower:
            return 24576
        elif "7900 xt" in GpuNameLower:
            return 20480
        elif "7800 xt" in GpuNameLower:
            return 16384
        elif "7700 xt" in GpuNameLower:
            return 12288
        elif "7600" in GpuNameLower:
            return 8192

        # AMD RX 6000 series
        elif "6900" in GpuNameLower:
            return 16384
        elif "6800" in GpuNameLower:
            return 16384
        elif "6700" in GpuNameLower:
            return 12288
        elif "6600" in GpuNameLower:
            return 8192
        elif "6500" in GpuNameLower:
            return 4096
        elif "6400" in GpuNameLower:
            return 4096

        # AMD RX 5000 series (Navi)
        elif "5700 xt" in GpuNameLower:
            return 8192
        elif "5700" in GpuNameLower:
            return 8192
        elif "5600 xt" in GpuNameLower:
            return 6144
        elif "5600" in GpuNameLower:
            return 6144
        elif "5500 xt" in GpuNameLower:
            return 8192  # Version 4GB ou 8GB

        # AMD RX 500 series (Polaris)
        elif "590" in GpuNameLower and "rx" in GpuNameLower:
            return 8192
        elif "580" in GpuNameLower and "rx" in GpuNameLower:
            return 8192  # Version 4GB ou 8GB
        elif "570" in GpuNameLower and "rx" in GpuNameLower:
            return 4096  # Version 4GB ou 8GB
        elif "560" in GpuNameLower and "rx" in GpuNameLower:
            return 4096
        elif "550" in GpuNameLower and "rx" in GpuNameLower:
            return 2048

        # AMD RX 400 series (Polaris)
        elif "480" in GpuNameLower and "rx" in GpuNameLower:
            return 8192  # Version 4GB ou 8GB
        elif "470" in GpuNameLower and "rx" in GpuNameLower:
            return 4096  # Version 4GB ou 8GB
        elif "460" in GpuNameLower and "rx" in GpuNameLower:
            return 4096

        # AMD Vega
        elif "vega 64" in GpuNameLower:
            return 8192
        elif "vega 56" in GpuNameLower:
            return 8192

        # Intel Arc
        elif "a770" in GpuNameLower:
            return 16384
        elif "a750" in GpuNameLower:
            return 8192
        elif "a580" in GpuNameLower:
            return 8192
        elif "a380" in GpuNameLower:
            return 6144
        elif "a310" in GpuNameLower:
            return 4096

        # Intel Integrated Graphics (valeurs basses car VRAM partagée)
        elif "iris xe" in GpuNameLower:
            return 1024  # Dépend de la RAM système allouée
        elif "iris plus" in GpuNameLower:
            return 512
        elif "uhd" in GpuNameLower and "intel" in GpuNameLower:
            return 512
        elif "hd graphics" in GpuNameLower or "hd 530" in GpuNameLower:
            return 512
        elif "intel" in GpuNameLower and ("graphics" in GpuNameLower or "hd" in GpuNameLower):
            return 512  # Intel intégré générique

        # NVIDIA Quadro (workstation)
        elif "quadro rtx" in GpuNameLower:
            return 16384  # Varie selon modèle
        elif "quadro" in GpuNameLower:
            return 8192  # Estimation moyenne

        # Valeur par défaut pour GPU inconnu
        # On suppose un GPU dédié avec au moins 2GB
        return 2048

    def IsIntegratedGpu(self, GpuName: str) -> bool:
        """
        Détermine si un GPU est intégré (pas dédié)

        Args:
            GpuName: Nom du GPU

        Returns:
            True si le GPU est intégré
        """
        GpuNameLower = GpuName.lower()

        # Patterns pour les GPU intégrés
        IntegratedPatterns = [
            "intel" in GpuNameLower and ("hd graphics" in GpuNameLower or
                                         "uhd" in GpuNameLower or
                                         "iris" in GpuNameLower or
                                         "hd 530" in GpuNameLower or
                                         "hd 630" in GpuNameLower or
                                         "hd 4" in GpuNameLower or
                                         "hd 5" in GpuNameLower or
                                         "hd 6" in GpuNameLower),
            "amd" in GpuNameLower and "vega" in GpuNameLower and "radeon" not in GpuNameLower,  # APU AMD
            "apu" in GpuNameLower,
        ]

        return any(IntegratedPatterns)

    def GetGpuScore(self, Gpu: Dict) -> int:
        """
        Calcule un score pour un GPU (plus haut = meilleur)

        Le score est basé sur:
        - La VRAM (principal facteur)
        - Le type de GPU (dédié vs intégré)
        - Le fabricant (NVIDIA > AMD > Intel pour le support Vulkan)

        Args:
            Gpu: Dictionnaire GPU avec 'name' et 'vram_mb'

        Returns:
            Score du GPU
        """
        GpuName = Gpu.get("name", "").lower()
        VramMb = Gpu.get("vram_mb", 0)

        # Score de base = VRAM
        Score = VramMb

        # Pénalité pour GPU intégré
        if self.IsIntegratedGpu(Gpu.get("name", "")):
            Score = Score // 4  # Divise par 4

        # Bonus pour GPU dédié NVIDIA (meilleur support Vulkan)
        if "nvidia" in GpuName or "geforce" in GpuName or "gtx" in GpuName or "rtx" in GpuName:
            Score += 500
        # Bonus moindre pour AMD dédié
        elif "radeon" in GpuName or "rx" in GpuName:
            Score += 300
        # Intel Arc (dédié, bon support Vulkan récent)
        elif "arc" in GpuName and ("a7" in GpuName or "a5" in GpuName or "a3" in GpuName):
            Score += 200

        return Score

    def SelectBestGpus(self, Gpus: List[Dict], MaxGpus: int = 1,
                       PreferDedicated: bool = True) -> List[int]:
        """
        Sélectionne les meilleurs GPU pour Real-ESRGAN

        Args:
            Gpus: Liste des GPU détectés
            MaxGpus: Nombre maximum de GPU à sélectionner (1 = mono-GPU, >1 = multi-GPU)
            PreferDedicated: Si True, préfère les GPU dédiés aux intégrés

        Returns:
            Liste des IDs des GPU sélectionnés (triés par score décroissant)
        """
        if not Gpus:
            return []

        # Filtre les GPU valides (id >= 0)
        ValidGpus = [g for g in Gpus if g.get("id", -1) >= 0]

        if not ValidGpus:
            return []

        # Si on préfère les GPU dédiés, filtre d'abord
        if PreferDedicated:
            DedicatedGpus = [g for g in ValidGpus if not self.IsIntegratedGpu(g.get("name", ""))]
            # Si on a des GPU dédiés, on les utilise en priorité
            if DedicatedGpus:
                ValidGpus = DedicatedGpus

        # Trie par score décroissant
        SortedGpus = sorted(ValidGpus, key=lambda g: self.GetGpuScore(g), reverse=True)

        # Retourne les N meilleurs IDs
        SelectedIds = [g["id"] for g in SortedGpus[:MaxGpus]]

        self.Logger.info(f"GPU sélectionnés: {SelectedIds}")
        return SelectedIds

    def GetRecommendedConfig(self, Hardware: Optional[Dict] = None,
                             UseMultiGpu: bool = False) -> Dict:
        """
        Génère une configuration de performance recommandée

        Args:
            Hardware: Matériel détecté (ou None pour détecter)
            UseMultiGpu: Si True, utilise tous les GPU dédiés disponibles

        Returns:
            Configuration de performance recommandée
        """
        if Hardware is None:
            Hardware = self.DetectAll()

        Gpus = Hardware.get("gpu", [])
        CpuCores = Hardware.get("cpu", {}).get("physical_cores", 1)

        # Sélectionne le(s) meilleur(s) GPU
        MaxGpus = 99 if UseMultiGpu else 1  # 99 = tous les GPU dédiés
        SelectedGpuIds = self.SelectBestGpus(Gpus, MaxGpus=MaxGpus, PreferDedicated=True)

        if not SelectedGpuIds:
            # Pas de GPU, mode CPU
            return {
                "gpu_ids": [],
                "tile_size": 32,
                "threads": {"load": 1, "process": 1, "save": 1}
            }

        # Trouve le GPU avec le moins de VRAM parmi les sélectionnés
        # (pour le tile size, on prend le minimum pour éviter les problèmes)
        SelectedGpus = [g for g in Gpus if g.get("id") in SelectedGpuIds]
        if SelectedGpus:
            MinVramGpu = min(SelectedGpus, key=lambda g: g.get("vram_mb", 2048))
            MinVram = MinVramGpu.get("vram_mb", 2048)
            GpuName = MinVramGpu.get("name", "")
        else:
            MinVram = 2048
            GpuName = ""

        # Calcule le tile size optimal basé sur la VRAM et génération GPU
        TileSize = self.GetRecommendedTileSize(MinVram, GpuName)

        # Calcule les threads recommandés
        Threads = self.GetRecommendedThreads(CpuCores, len(SelectedGpuIds))

        Config = {
            "gpu_ids": SelectedGpuIds,
            "tile_size": TileSize,
            "threads": Threads
        }

        self.Logger.info(f"Configuration recommandée: GPU={SelectedGpuIds}, tile={TileSize}, threads={Threads}")
        return Config

    def GetRecommendedTileSize(self, VramMb: int, GpuName: str = "") -> int:
        """
        Calcule le tile size recommandé basé sur la VRAM et génération GPU

        Args:
            VramMb: VRAM en MB
            GpuName: Nom du GPU (optionnel, pour ajuster selon la génération)

        Returns:
            Tile size recommandé
        """
        # Tile size de base selon la VRAM (valeurs optimisées)
        if VramMb >= 24576:
            BaseTileSize = 1280
        elif VramMb >= 16384:
            BaseTileSize = 1024
        elif VramMb >= 12288:
            BaseTileSize = 896
        elif VramMb >= 8192:
            BaseTileSize = 640
        elif VramMb >= 6144:
            BaseTileSize = 448
        elif VramMb >= 4096:
            BaseTileSize = 320
        elif VramMb >= 2048:
            BaseTileSize = 128
        else:
            BaseTileSize = 64

        # Applique multiplicateur de génération si le nom est fourni
        if GpuName:
            GpuNameLower = GpuName.lower()
            Multiplier = 1.0

            # RTX 40 series (Ada Lovelace) - très efficace
            if any(x in GpuNameLower for x in ["4090", "4080", "4070", "4060", "4050"]):
                Multiplier = 1.25
            # RTX 30 series (Ampere)
            elif any(x in GpuNameLower for x in ["3090", "3080", "3070", "3060", "3050"]):
                Multiplier = 1.15
            # GTX 10 series (Pascal) - un peu moins efficace
            elif any(x in GpuNameLower for x in ["1080", "1070", "1060", "1050"]):
                Multiplier = 0.9

            # Réduit pour les GPU laptop (moins de bande passante mémoire, throttling thermique)
            LaptopIndicators = ['laptop', 'mobile', 'max-q', 'max q']
            if any(indicator in GpuNameLower for indicator in LaptopIndicators):
                Multiplier *= 0.75
                self.Logger.debug(f"GPU laptop détecté: {GpuName}, facteur réduit")

            BaseTileSize = int(BaseTileSize * Multiplier)
            # Arrondit à un multiple de 32
            BaseTileSize = (BaseTileSize // 32) * 32
            # Assure un minimum raisonnable
            BaseTileSize = max(BaseTileSize, 32)
            # Limite max
            BaseTileSize = min(BaseTileSize, 2048)

        return BaseTileSize

    def GetRecommendedThreads(self, CpuCores: int, GpuCount: int) -> Dict:
        """
        Calcule les threads recommandés

        Args:
            CpuCores: Nombre de coeurs CPU
            GpuCount: Nombre de GPU

        Returns:
            Configuration des threads
        """
        # Load threads: généralement 1-2 suffit (I/O bound)
        LoadThreads = min(2, CpuCores)

        # Process threads: dépend du nombre de GPU
        ProcessThreads = min(4, max(2, CpuCores // 2))

        # Save threads: similaire à load
        SaveThreads = min(2, CpuCores)

        return {
            "load": LoadThreads,
            "process": ProcessThreads,
            "save": SaveThreads
        }


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    print("=== Test HardwareDetector ===\n")

    Detector = HardwareDetector()
    Hardware = Detector.DetectAll()

    print("\n--- CPU ---")
    print(f"Nom: {Hardware['cpu']['name']}")
    print(f"Coeurs physiques: {Hardware['cpu']['physical_cores']}")
    print(f"Coeurs logiques: {Hardware['cpu']['logical_cores']}")

    print("\n--- RAM ---")
    print(f"Total: {Hardware['ram']['total_gb']} GB")
    print(f"Disponible: {Hardware['ram']['available_gb']} GB")
    print(f"Utilisée: {Hardware['ram']['percent_used']}%")

    print("\n--- GPU ---")
    for Gpu in Hardware['gpu']:
        VramStr = f" ({Gpu.get('vram_mb', '?')} MB)" if Gpu.get('vram_mb') else ""
        IsIntegrated = Detector.IsIntegratedGpu(Gpu.get('name', ''))
        TypeStr = "(intégré)" if IsIntegrated else "(dédié)"
        Score = Detector.GetGpuScore(Gpu)
        print(f"[{Gpu['id']}] {Gpu['name']}{VramStr} {TypeStr} - Score: {Score}")

        if Gpu['id'] >= 0 and Gpu.get('vram_mb'):
            TileSize = Detector.GetRecommendedTileSize(Gpu['vram_mb'], Gpu.get('name', ''))
            print(f"    Tile size recommandé: {TileSize}")

    print("\n--- Sélection GPU intelligente ---")
    # Sélection du meilleur GPU (mono-GPU)
    BestGpuIds = Detector.SelectBestGpus(Hardware['gpu'], MaxGpus=1)
    print(f"Meilleur GPU: {BestGpuIds}")

    # Sélection multi-GPU (tous les GPU dédiés)
    AllDedicatedIds = Detector.SelectBestGpus(Hardware['gpu'], MaxGpus=99)
    print(f"Tous les GPU dédiés: {AllDedicatedIds}")

    print("\n--- Configuration recommandée ---")
    Config = Detector.GetRecommendedConfig(Hardware, UseMultiGpu=False)
    print(f"Mode mono-GPU: GPU={Config['gpu_ids']}, tile={Config['tile_size']}")

    ConfigMulti = Detector.GetRecommendedConfig(Hardware, UseMultiGpu=True)
    print(f"Mode multi-GPU: GPU={ConfigMulti['gpu_ids']}, tile={ConfigMulti['tile_size']}")

    print("\n--- Threads recommandés ---")
    GpuCount = len([g for g in Hardware['gpu'] if g['id'] >= 0])
    Threads = Detector.GetRecommendedThreads(Hardware['cpu']['physical_cores'], GpuCount)
    print(f"Load: {Threads['load']}, Process: {Threads['process']}, Save: {Threads['save']}")
