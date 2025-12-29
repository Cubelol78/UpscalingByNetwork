"""
Gestionnaire de configuration des performances pour Real-ESRGAN
Gère la sauvegarde et le chargement des paramètres de performance
"""

import os
import json
from typing import Dict, List, Optional
from pathlib import Path

from shared.utils.logger import GetModuleLogger


class PerformancePresets:
    """Presets de performance selon le matériel"""

    # Tile size selon la VRAM (en MB)
    TILE_SIZE_MAP = {
        2048: 128,
        4096: 256,
        6144: 384,
        8192: 512,
        12288: 768,
        16384: 1024,
        24576: 1024
    }

    # Threads par défaut
    DEFAULT_LOAD_THREADS = 1
    DEFAULT_PROCESS_THREADS = 2
    DEFAULT_SAVE_THREADS = 2

    # Valeurs min/max
    MIN_TILE_SIZE = 32
    MAX_TILE_SIZE = 2048
    MIN_THREADS = 1
    MAX_THREADS = 16


class PerformanceConfigManager:
    """Gestionnaire de configuration des performances"""

    DEFAULT_CONFIG = {
        "auto_detect": True,
        "tile_size": 0,  # 0 = auto
        "gpu_ids": [],   # vide = auto (utilise le premier GPU)
        "threads": {
            "load": PerformancePresets.DEFAULT_LOAD_THREADS,
            "process": PerformancePresets.DEFAULT_PROCESS_THREADS,
            "save": PerformancePresets.DEFAULT_SAVE_THREADS
        },
        "tta_mode": False,
        "output_format": "png",
        "first_run": True
    }

    def __init__(self, ConfigDir: Optional[str] = None):
        """
        Initialise le gestionnaire de configuration

        Args:
            ConfigDir: Répertoire de configuration (par défaut: ~/.upscaling_client/)
        """
        self.Logger = GetModuleLogger("PerformanceConfig")

        if ConfigDir:
            self.ConfigDir = ConfigDir
        else:
            self.ConfigDir = os.path.join(
                str(Path.home()),
                ".upscaling_client"
            )

        self.ConfigPath = os.path.join(self.ConfigDir, "performance.json")
        self.Config = None

        # Crée le répertoire si nécessaire
        os.makedirs(self.ConfigDir, exist_ok=True)

    def Load(self) -> Dict:
        """
        Charge la configuration depuis le fichier

        Returns:
            Configuration chargée
        """
        try:
            if os.path.exists(self.ConfigPath):
                with open(self.ConfigPath, 'r', encoding='utf-8') as f:
                    self.Config = json.load(f)

                # Fusionne avec les valeurs par défaut pour les clés manquantes
                self.Config = self._MergeWithDefaults(self.Config)
                self.Logger.info("Configuration de performance chargée")
            else:
                self.Config = self.DEFAULT_CONFIG.copy()
                self.Logger.info("Première exécution - configuration par défaut")

            return self.Config

        except Exception as e:
            self.Logger.error(f"Erreur lors du chargement de la configuration: {e}")
            self.Config = self.DEFAULT_CONFIG.copy()
            return self.Config

    def Save(self, Config: Optional[Dict] = None) -> bool:
        """
        Sauvegarde la configuration dans le fichier

        Args:
            Config: Configuration à sauvegarder (utilise self.Config si None)

        Returns:
            True si succès
        """
        try:
            if Config is not None:
                self.Config = Config

            if self.Config is None:
                self.Config = self.DEFAULT_CONFIG.copy()

            # Marque comme n'étant plus la première exécution
            self.Config["first_run"] = False

            with open(self.ConfigPath, 'w', encoding='utf-8') as f:
                json.dump(self.Config, f, indent=2, ensure_ascii=False)

            self.Logger.info("Configuration de performance sauvegardée")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")
            return False

    def _MergeWithDefaults(self, Config: Dict) -> Dict:
        """Fusionne la config chargée avec les valeurs par défaut"""
        Merged = self.DEFAULT_CONFIG.copy()

        for Key, Value in Config.items():
            if Key == "threads" and isinstance(Value, dict):
                Merged["threads"] = {
                    **self.DEFAULT_CONFIG["threads"],
                    **Value
                }
            else:
                Merged[Key] = Value

        return Merged

    def Get(self, Key: str, Default=None):
        """
        Récupère une valeur de configuration

        Args:
            Key: Clé de configuration
            Default: Valeur par défaut si la clé n'existe pas

        Returns:
            Valeur de configuration
        """
        if self.Config is None:
            self.Load()

        return self.Config.get(Key, Default)

    def Set(self, Key: str, Value) -> bool:
        """
        Définit une valeur de configuration

        Args:
            Key: Clé de configuration
            Value: Valeur à définir

        Returns:
            True si succès
        """
        if self.Config is None:
            self.Load()

        self.Config[Key] = Value
        return self.Save()

    def GetAll(self) -> Dict:
        """
        Récupère toute la configuration

        Returns:
            Configuration complète
        """
        if self.Config is None:
            self.Load()

        return self.Config.copy()

    def Reset(self) -> bool:
        """
        Réinitialise la configuration aux valeurs par défaut

        Returns:
            True si succès
        """
        self.Config = self.DEFAULT_CONFIG.copy()
        return self.Save()

    def IsFirstRun(self) -> bool:
        """
        Vérifie si c'est la première exécution

        Returns:
            True si première exécution
        """
        if self.Config is None:
            self.Load()

        return self.Config.get("first_run", True)

    def AutoConfigure(self, HardwareInfo: Dict) -> Dict:
        """
        Configure automatiquement basé sur le matériel détecté

        Args:
            HardwareInfo: Informations matérielles de HardwareDetector

        Returns:
            Configuration optimale
        """
        try:
            Config = self.DEFAULT_CONFIG.copy()
            Config["auto_detect"] = True

            # Configuration des GPU
            Gpus = HardwareInfo.get("gpu", [])
            ValidGpus = [g for g in Gpus if g.get("id", -1) >= 0]

            if ValidGpus:
                # Utilise le premier GPU par défaut
                PrimaryGpu = ValidGpus[0]
                VramMb = PrimaryGpu.get("vram_mb", 4096)

                # Calcule le tile size optimal
                Config["tile_size"] = self.GetTileSizeForVram(VramMb)

                # Par défaut, utilise tous les GPU disponibles
                if len(ValidGpus) > 1:
                    Config["gpu_ids"] = [g["id"] for g in ValidGpus]
                else:
                    Config["gpu_ids"] = [PrimaryGpu["id"]]

                self.Logger.info(f"GPU configuré: {PrimaryGpu['name']}")
                self.Logger.info(f"Tile size auto: {Config['tile_size']}")
            else:
                # Pas de GPU, utilise CPU
                Config["gpu_ids"] = [-1]
                Config["tile_size"] = 128  # Petit tile size pour CPU
                self.Logger.warning("Pas de GPU détecté, utilisation du CPU")

            # Configuration des threads
            CpuCores = HardwareInfo.get("cpu", {}).get("physical_cores", 4)
            Config["threads"] = self.GetThreadConfig(CpuCores, len(ValidGpus))

            self.Config = Config
            return Config

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'auto-configuration: {e}")
            return self.DEFAULT_CONFIG.copy()

    def GetTileSizeForVram(self, VramMb: int) -> int:
        """
        Calcule le tile size optimal pour une quantité de VRAM

        Args:
            VramMb: VRAM en MB

        Returns:
            Tile size recommandé
        """
        # Trouve le tile size approprié
        TileSize = PerformancePresets.MIN_TILE_SIZE

        for VramThreshold, Size in sorted(PerformancePresets.TILE_SIZE_MAP.items()):
            if VramMb >= VramThreshold:
                TileSize = Size
            else:
                break

        return TileSize

    def GetThreadConfig(self, CpuCores: int, GpuCount: int) -> Dict:
        """
        Calcule la configuration des threads optimale

        Args:
            CpuCores: Nombre de coeurs CPU
            GpuCount: Nombre de GPU

        Returns:
            Configuration des threads
        """
        # Load threads: I/O bound, peu de parallélisme nécessaire
        LoadThreads = min(2, max(1, CpuCores // 4))

        # Process threads: dépend du GPU
        ProcessThreads = min(4, max(2, CpuCores // 2))

        # Save threads: I/O bound
        SaveThreads = min(2, max(1, CpuCores // 4))

        return {
            "load": LoadThreads,
            "process": ProcessThreads,
            "save": SaveThreads
        }

    def FormatThreadsForCommand(self, Threads: Optional[Dict] = None, GpuCount: int = 1) -> str:
        """
        Formate les threads pour la ligne de commande Real-ESRGAN

        Args:
            Threads: Configuration des threads (utilise self.Config si None)
            GpuCount: Nombre de GPU utilisés

        Returns:
            String formatée pour l'option -j (ex: "1:2:2" ou "1:2,2:2")
        """
        if Threads is None:
            if self.Config is None:
                self.Load()
            Threads = self.Config.get("threads", {})

        Load = Threads.get("load", PerformancePresets.DEFAULT_LOAD_THREADS)
        Process = Threads.get("process", PerformancePresets.DEFAULT_PROCESS_THREADS)
        Save = Threads.get("save", PerformancePresets.DEFAULT_SAVE_THREADS)

        # Pour multi-GPU, le format est "load:proc,proc,proc:save"
        if GpuCount > 1:
            ProcessStr = ",".join([str(Process)] * GpuCount)
            return f"{Load}:{ProcessStr}:{Save}"
        else:
            return f"{Load}:{Process}:{Save}"

    def FormatGpuIdsForCommand(self, GpuIds: Optional[List[int]] = None) -> str:
        """
        Formate les GPU IDs pour la ligne de commande Real-ESRGAN

        Args:
            GpuIds: Liste des IDs GPU (utilise self.Config si None)

        Returns:
            String formatée pour l'option -g (ex: "0" ou "0,1,2")
        """
        if GpuIds is None:
            if self.Config is None:
                self.Load()
            GpuIds = self.Config.get("gpu_ids", [])

        if not GpuIds:
            return ""  # Auto-détection par Real-ESRGAN

        return ",".join(map(str, GpuIds))

    def FormatTileSizeForCommand(self, TileSize: Optional[int] = None, GpuCount: int = 1) -> str:
        """
        Formate le tile size pour la ligne de commande Real-ESRGAN

        Args:
            TileSize: Taille des tuiles (utilise self.Config si None)
            GpuCount: Nombre de GPU utilisés

        Returns:
            String formatée pour l'option -t (ex: "256" ou "256,256")
        """
        if TileSize is None:
            if self.Config is None:
                self.Load()
            TileSize = self.Config.get("tile_size", 0)

        if TileSize == 0:
            return ""  # Auto par Real-ESRGAN

        # Pour multi-GPU, on peut spécifier un tile size par GPU
        if GpuCount > 1:
            return ",".join([str(TileSize)] * GpuCount)
        else:
            return str(TileSize)

    def GetRealEsrganParams(self) -> Dict:
        """
        Récupère tous les paramètres formatés pour Real-ESRGAN

        Returns:
            Dictionnaire avec les paramètres formatés
        """
        if self.Config is None:
            self.Load()

        GpuIds = self.Config.get("gpu_ids", [])
        GpuCount = len(GpuIds) if GpuIds else 1

        return {
            "tile_size": self.FormatTileSizeForCommand(GpuCount=GpuCount),
            "gpu_ids": self.FormatGpuIdsForCommand(),
            "threads": self.FormatThreadsForCommand(GpuCount=GpuCount),
            "tta_mode": self.Config.get("tta_mode", False),
            "output_format": self.Config.get("output_format", "png")
        }


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    print("=== Test PerformanceConfigManager ===\n")

    Manager = PerformanceConfigManager()
    Config = Manager.Load()

    print("Configuration actuelle:")
    print(json.dumps(Config, indent=2))

    print("\n--- Test Auto-Configuration ---")

    # Simule du matériel
    FakeHardware = {
        "cpu": {
            "physical_cores": 8,
            "logical_cores": 16,
            "name": "Intel Core i7-12700K"
        },
        "ram": {
            "total_gb": 32,
            "available_gb": 24
        },
        "gpu": [
            {"id": 0, "name": "NVIDIA GeForce RTX 3080", "vram_mb": 10240},
            {"id": 1, "name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288}
        ]
    }

    AutoConfig = Manager.AutoConfigure(FakeHardware)
    print("\nConfiguration auto-générée:")
    print(json.dumps(AutoConfig, indent=2))

    print("\n--- Paramètres Real-ESRGAN ---")
    Params = Manager.GetRealEsrganParams()
    print(f"Tile size: {Params['tile_size']}")
    print(f"GPU IDs: {Params['gpu_ids']}")
    print(f"Threads: {Params['threads']}")
    print(f"TTA mode: {Params['tta_mode']}")
