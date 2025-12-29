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

    # Tile size selon la VRAM (en MB) - optimisé pour meilleure utilisation GPU
    # Ces valeurs sont plus agressives pour les architectures modernes
    TILE_SIZE_MAP = {
        2048: 128,
        4096: 320,    # Augmenté de 256
        6144: 448,    # Augmenté de 384
        8192: 640,    # Augmenté de 512 - RTX 4060/3070/3060Ti
        12288: 896,   # Augmenté de 768
        16384: 1024,
        24576: 1280   # Augmenté de 1024
    }

    # Multiplicateurs de tile size par génération GPU (architecture plus efficace)
    GPU_GENERATION_MULTIPLIER = {
        "rtx40": 1.25,   # Ada Lovelace - très efficace
        "rtx30": 1.15,   # Ampere
        "rtx20": 1.0,    # Turing
        "gtx16": 1.0,    # Turing
        "gtx10": 0.9,    # Pascal
        "default": 1.0
    }

    # Threads par défaut - augmentés pour meilleure utilisation
    DEFAULT_LOAD_THREADS = 2
    DEFAULT_PROCESS_THREADS = 4   # Augmenté de 2 à 4
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

    def _GetGpuGeneration(self, GpuName: str) -> str:
        """
        Détecte la génération du GPU NVIDIA

        Args:
            GpuName: Nom du GPU

        Returns:
            Clé de génération (rtx40, rtx30, rtx20, gtx16, gtx10, default)
        """
        GpuNameLower = GpuName.lower()

        # RTX 40 series (Ada Lovelace)
        if any(x in GpuNameLower for x in ["4090", "4080", "4070", "4060", "4050"]):
            return "rtx40"
        # RTX 30 series (Ampere)
        elif any(x in GpuNameLower for x in ["3090", "3080", "3070", "3060", "3050"]):
            return "rtx30"
        # RTX 20 series (Turing)
        elif any(x in GpuNameLower for x in ["2080", "2070", "2060"]):
            return "rtx20"
        # GTX 16 series (Turing)
        elif any(x in GpuNameLower for x in ["1660", "1650"]):
            return "gtx16"
        # GTX 10 series (Pascal)
        elif any(x in GpuNameLower for x in ["1080", "1070", "1060", "1050"]):
            return "gtx10"
        else:
            return "default"

    def _IsIntegratedGpu(self, GpuName: str) -> bool:
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
                                         "hd 4" in GpuNameLower or
                                         "hd 5" in GpuNameLower or
                                         "hd 6" in GpuNameLower),
            "amd" in GpuNameLower and "vega" in GpuNameLower and "radeon" not in GpuNameLower,
            "apu" in GpuNameLower,
        ]

        return any(IntegratedPatterns)

    def _GetGpuScore(self, Gpu: Dict) -> int:
        """
        Calcule un score pour un GPU (plus haut = meilleur)

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
        if self._IsIntegratedGpu(Gpu.get("name", "")):
            Score = Score // 4

        # Bonus pour GPU dédié NVIDIA
        if "nvidia" in GpuName or "geforce" in GpuName or "gtx" in GpuName or "rtx" in GpuName:
            Score += 500
        elif "radeon" in GpuName or "rx" in GpuName:
            Score += 300
        elif "arc" in GpuName:
            Score += 200

        return Score

    def _SelectBestGpus(self, Gpus: List[Dict], UseMultiGpu: bool = False) -> List[int]:
        """
        Sélectionne les meilleurs GPU pour Real-ESRGAN

        Args:
            Gpus: Liste des GPU détectés
            UseMultiGpu: Si True, sélectionne tous les GPU dédiés

        Returns:
            Liste des IDs des GPU sélectionnés
        """
        if not Gpus:
            return []

        # Filtre les GPU valides (id >= 0)
        ValidGpus = [g for g in Gpus if g.get("id", -1) >= 0]

        if not ValidGpus:
            return []

        # Filtre les GPU dédiés
        DedicatedGpus = [g for g in ValidGpus if not self._IsIntegratedGpu(g.get("name", ""))]

        # Si on a des GPU dédiés, on les utilise en priorité
        if DedicatedGpus:
            ValidGpus = DedicatedGpus

        # Trie par score décroissant
        SortedGpus = sorted(ValidGpus, key=lambda g: self._GetGpuScore(g), reverse=True)

        if UseMultiGpu:
            # Retourne tous les GPU dédiés
            return [g["id"] for g in SortedGpus]
        else:
            # Retourne uniquement le meilleur GPU
            return [SortedGpus[0]["id"]] if SortedGpus else []

    def AutoConfigure(self, HardwareInfo: Dict, UseMultiGpu: bool = False) -> Dict:
        """
        Configure automatiquement basé sur le matériel détecté
        Utilise une sélection intelligente des GPU (préfère les dédiés)

        Args:
            HardwareInfo: Informations matérielles de HardwareDetector
            UseMultiGpu: Si True, utilise tous les GPU dédiés disponibles

        Returns:
            Configuration optimale
        """
        try:
            Config = self.DEFAULT_CONFIG.copy()
            Config["auto_detect"] = True

            # Configuration des GPU avec sélection intelligente
            Gpus = HardwareInfo.get("gpu", [])
            SelectedGpuIds = self._SelectBestGpus(Gpus, UseMultiGpu=UseMultiGpu)
            SelectedGpus = []  # Initialise pour éviter erreur de référence

            if SelectedGpuIds:
                Config["gpu_ids"] = SelectedGpuIds

                # Trouve les GPU sélectionnés pour calculer le tile size
                SelectedGpus = [g for g in Gpus if g.get("id") in SelectedGpuIds]

                # Utilise la VRAM minimale et le nom du GPU le plus faible
                if SelectedGpus:
                    MinVramGpu = min(SelectedGpus, key=lambda g: g.get("vram_mb", 2048))
                    MinVram = MinVramGpu.get("vram_mb", 2048)
                    GpuName = MinVramGpu.get("name", "")
                else:
                    MinVram = 2048
                    GpuName = ""

                # Calcule le tile size avec le multiplicateur de génération
                Config["tile_size"] = self.GetTileSizeForVram(MinVram, GpuName)

                # Log les GPU sélectionnés
                for Gpu in SelectedGpus:
                    IsIntegrated = self._IsIntegratedGpu(Gpu.get("name", ""))
                    GpuType = "(intégré)" if IsIntegrated else "(dédié)"
                    Generation = self._GetGpuGeneration(Gpu.get("name", ""))
                    self.Logger.info(f"GPU sélectionné: {Gpu['name']} {GpuType} [génération: {Generation}]")

                self.Logger.info(f"Tile size auto: {Config['tile_size']} (basé sur {MinVram} MB VRAM, GPU: {GpuName})")
            else:
                # Pas de GPU, utilise CPU
                Config["gpu_ids"] = []
                Config["tile_size"] = 32  # Petit tile size pour CPU
                self.Logger.warning("Pas de GPU détecté, utilisation du CPU")

            # Configuration des threads (utilise le nom du GPU pour ajuster)
            CpuCores = HardwareInfo.get("cpu", {}).get("physical_cores", 4)
            BestGpuName = SelectedGpus[0].get("name", "") if SelectedGpus else ""
            Config["threads"] = self.GetThreadConfig(CpuCores, len(SelectedGpuIds), BestGpuName)

            self.Config = Config
            return Config

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'auto-configuration: {e}")
            return self.DEFAULT_CONFIG.copy()

    def GetTileSizeForVram(self, VramMb: int, GpuName: str = "") -> int:
        """
        Calcule le tile size optimal pour une quantité de VRAM et génération GPU

        Args:
            VramMb: VRAM en MB
            GpuName: Nom du GPU (optionnel, pour appliquer le multiplicateur de génération)

        Returns:
            Tile size recommandé
        """
        # Trouve le tile size de base
        TileSize = PerformancePresets.MIN_TILE_SIZE

        for VramThreshold, Size in sorted(PerformancePresets.TILE_SIZE_MAP.items()):
            if VramMb >= VramThreshold:
                TileSize = Size
            else:
                break

        # Applique le multiplicateur de génération si le nom du GPU est fourni
        if GpuName:
            Generation = self._GetGpuGeneration(GpuName)
            Multiplier = PerformancePresets.GPU_GENERATION_MULTIPLIER.get(Generation, 1.0)
            TileSize = int(TileSize * Multiplier)

            # Arrondit à un multiple de 32 (meilleur pour le GPU)
            TileSize = (TileSize // 32) * 32

            # Limite au maximum
            TileSize = min(TileSize, PerformancePresets.MAX_TILE_SIZE)

            self.Logger.debug(f"Tile size pour {GpuName}: base={TileSize//Multiplier:.0f}, "
                            f"multiplier={Multiplier}x ({Generation}), final={TileSize}")

        return TileSize

    def GetThreadConfig(self, CpuCores: int, GpuCount: int, GpuName: str = "") -> Dict:
        """
        Calcule la configuration des threads optimale

        Args:
            CpuCores: Nombre de coeurs CPU
            GpuCount: Nombre de GPU
            GpuName: Nom du GPU principal (pour ajuster selon la génération)

        Returns:
            Configuration des threads
        """
        # Détermine si c'est un GPU moderne (RTX 30/40)
        Generation = self._GetGpuGeneration(GpuName) if GpuName else "default"
        IsModernGpu = Generation in ["rtx40", "rtx30"]

        # Load threads: I/O bound, un peu plus pour les GPU modernes
        LoadThreads = min(3 if IsModernGpu else 2, max(1, CpuCores // 3))

        # Process threads: plus élevé pour les GPU modernes qui sont rapides
        # Les GPU modernes peuvent traiter plus vite, donc on augmente le parallelisme
        if IsModernGpu:
            ProcessThreads = min(6, max(4, CpuCores // 2))
        else:
            ProcessThreads = min(4, max(2, CpuCores // 2))

        # Save threads: I/O bound, similaire à load
        SaveThreads = min(3 if IsModernGpu else 2, max(1, CpuCores // 3))

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
