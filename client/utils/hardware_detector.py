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

        # Pattern: [0] NVIDIA GeForce RTX 3080
        # ou: [0 NVIDIA GeForce RTX 3080]
        Patterns = [
            r'\[(\d+)\]\s+(.+?)(?:\n|$)',  # [0] GPU Name
            r'gpu\s*(\d+)\s*[:=]\s*(.+?)(?:\n|$)',  # gpu 0: GPU Name
            r'device\s*(\d+)\s*[:=]\s*(.+?)(?:\n|$)',  # device 0: GPU Name
        ]

        for Pattern in Patterns:
            Matches = re.findall(Pattern, Output, re.IGNORECASE)
            if Matches:
                for Match in Matches:
                    GpuId = int(Match[0])
                    GpuName = Match[1].strip()
                    # Ignore les lignes qui ne ressemblent pas à un nom de GPU
                    if len(GpuName) > 3 and not GpuName.startswith('-'):
                        Gpus.append({
                            "id": GpuId,
                            "name": GpuName,
                            "vram_mb": self._EstimateVram(GpuName)
                        })
                break

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
        elif "4070 ti" in GpuNameLower:
            return 12288
        elif "4070" in GpuNameLower:
            return 12288
        elif "4060 ti" in GpuNameLower:
            return 8192
        elif "4060" in GpuNameLower:
            return 8192

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
        elif "1070" in GpuNameLower:
            return 8192
        elif "1060" in GpuNameLower:
            return 6144
        elif "1050" in GpuNameLower:
            return 4096

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

        # Intel Arc
        elif "a770" in GpuNameLower:
            return 16384
        elif "a750" in GpuNameLower:
            return 8192
        elif "a380" in GpuNameLower:
            return 6144

        # Valeur par défaut
        return 4096

    def GetRecommendedTileSize(self, VramMb: int) -> int:
        """
        Calcule le tile size recommandé basé sur la VRAM

        Args:
            VramMb: VRAM en MB

        Returns:
            Tile size recommandé
        """
        if VramMb >= 16384:
            return 1024
        elif VramMb >= 12288:
            return 768
        elif VramMb >= 8192:
            return 512
        elif VramMb >= 6144:
            return 384
        elif VramMb >= 4096:
            return 256
        elif VramMb >= 2048:
            return 128
        else:
            return 64

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
        print(f"[{Gpu['id']}] {Gpu['name']}{VramStr}")

        if Gpu['id'] >= 0 and Gpu.get('vram_mb'):
            TileSize = Detector.GetRecommendedTileSize(Gpu['vram_mb'])
            print(f"    Tile size recommandé: {TileSize}")

    print("\n--- Threads recommandés ---")
    GpuCount = len([g for g in Hardware['gpu'] if g['id'] >= 0])
    Threads = Detector.GetRecommendedThreads(Hardware['cpu']['physical_cores'], GpuCount)
    print(f"Load: {Threads['load']}, Process: {Threads['process']}, Save: {Threads['save']}")
