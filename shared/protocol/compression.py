"""
Module de compression pour les transferts réseau
Supporte zstd (prioritaire) avec fallback sur zlib
"""

import zlib
from typing import List, Optional

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import CompressionConfig


class CompressionError(Exception):
    """Exception pour les erreurs de compression/décompression"""
    pass


class CompressionHandler:
    """Gestionnaire de compression avec support zstd et fallback zlib"""

    ALGO_NONE = "none"
    ALGO_ZSTD = "zstd"
    ALGO_ZLIB = "zlib"

    # Niveaux de compression par défaut (valeurs natives)
    ZSTD_LEVEL = 3   # zstd: 1-22, 3 = bon équilibre vitesse/compression
    ZLIB_LEVEL = 6   # zlib: 1-9, 6 = défaut Python

    def __init__(self):
        """Initialise le gestionnaire de compression"""
        self.Logger = GetModuleLogger("CompressionHandler")
        self.Algorithm = self.ALGO_NONE
        self.Level = CompressionConfig.LEVEL_DEFAULT  # Niveau commun (1-10)
        self.ZstdAvailable = self._CheckZstdAvailable()
        self.ZstdCompressor = None
        self.ZstdDecompressor = None

        if self.ZstdAvailable:
            self._InitZstd()

    def _CheckZstdAvailable(self) -> bool:
        """
        Vérifie si zstd est disponible

        Returns:
            True si zstd est installé
        """
        try:
            import zstd
            return True
        except ImportError:
            self.Logger.debug("zstd non disponible, fallback sur zlib")
            return False

    def _InitZstd(self):
        """Initialise les compresseurs zstd"""
        try:
            import zstd
            NativeLevel = self._ConvertToNativeLevel()
            self.ZstdCompressor = zstd.ZstdCompressor(level=NativeLevel)
            self.ZstdDecompressor = zstd.ZstdDecompressor()
        except Exception as e:
            self.Logger.warning(f"Erreur initialisation zstd: {e}")
            self.ZstdAvailable = False

    def GetSupportedAlgorithms(self) -> List[str]:
        """
        Retourne les algorithmes supportés (pour négociation handshake)
        L'ordre indique la préférence (zstd > zlib > none)

        Returns:
            Liste des algorithmes supportés
        """
        Algorithms = []

        if self.ZstdAvailable:
            Algorithms.append(self.ALGO_ZSTD)

        # zlib est toujours disponible (module Python natif)
        Algorithms.append(self.ALGO_ZLIB)

        # none est toujours supporté (pas de compression)
        Algorithms.append(self.ALGO_NONE)

        return Algorithms

    def SetAlgorithm(self, Algorithm: str):
        """
        Définit l'algorithme à utiliser

        Args:
            Algorithm: Algorithme de compression (none, zstd, zlib)
        """
        if Algorithm == self.ALGO_ZSTD and not self.ZstdAvailable:
            self.Logger.warning("zstd demandé mais non disponible, fallback sur zlib")
            Algorithm = self.ALGO_ZLIB

        self.Algorithm = Algorithm
        self.Logger.info(f"Compression configurée: {Algorithm}")

    def Compress(self, Data: bytes) -> bytes:
        """
        Compresse les données selon l'algorithme configuré

        Args:
            Data: Données à compresser

        Returns:
            Données compressées (ou originales si compression désactivée)

        Raises:
            CompressionError: Si la compression échoue
        """
        if self.Algorithm == self.ALGO_NONE:
            return Data

        try:
            if self.Algorithm == self.ALGO_ZSTD and self.ZstdAvailable:
                return self._CompressZstd(Data)
            elif self.Algorithm == self.ALGO_ZLIB:
                return self._CompressZlib(Data)
            else:
                return Data
        except Exception as e:
            self.Logger.error(f"Erreur de compression ({self.Algorithm}): {e}")
            raise CompressionError(f"Échec compression {self.Algorithm}: {e}")

    def Decompress(self, Data: bytes) -> bytes:
        """
        Décompresse les données selon l'algorithme configuré

        Args:
            Data: Données compressées

        Returns:
            Données décompressées

        Raises:
            CompressionError: Si la décompression échoue
        """
        if self.Algorithm == self.ALGO_NONE:
            return Data

        try:
            if self.Algorithm == self.ALGO_ZSTD and self.ZstdAvailable:
                return self._DecompressZstd(Data)
            elif self.Algorithm == self.ALGO_ZLIB:
                return self._DecompressZlib(Data)
            else:
                return Data
        except Exception as e:
            self.Logger.error(f"Erreur de décompression ({self.Algorithm}): {e}")
            raise CompressionError(f"Échec décompression {self.Algorithm}: {e}")

    def _CompressZstd(self, Data: bytes) -> bytes:
        """Compresse avec zstd"""
        if self.ZstdCompressor is None:
            self._InitZstd()

        return self.ZstdCompressor.compress(Data)

    def _DecompressZstd(self, Data: bytes) -> bytes:
        """Décompresse avec zstd"""
        if self.ZstdDecompressor is None:
            self._InitZstd()

        return self.ZstdDecompressor.decompress(Data)

    def _CompressZlib(self, Data: bytes) -> bytes:
        """Compresse avec zlib"""
        NativeLevel = self._ConvertToNativeLevel()
        return zlib.compress(Data, level=NativeLevel)

    def _DecompressZlib(self, Data: bytes) -> bytes:
        """Décompresse avec zlib"""
        return zlib.decompress(Data)

    def GetCompressionRatio(self, OriginalSize: int, CompressedSize: int) -> float:
        """
        Calcule le ratio de compression

        Args:
            OriginalSize: Taille originale en bytes
            CompressedSize: Taille compressée en bytes

        Returns:
            Ratio de compression (ex: 0.6 = 60% de la taille originale)
        """
        if OriginalSize == 0:
            return 1.0
        return CompressedSize / OriginalSize

    def IsEnabled(self) -> bool:
        """
        Vérifie si la compression est activée

        Returns:
            True si un algorithme de compression est configuré
        """
        return self.Algorithm != self.ALGO_NONE

    def GetAlgorithm(self) -> str:
        """
        Retourne l'algorithme actuellement configuré

        Returns:
            Nom de l'algorithme
        """
        return self.Algorithm

    def SetLevel(self, Level: int):
        """
        Définit le niveau de compression (échelle commune 1-10)

        Args:
            Level: Niveau de compression (1=rapide, 10=max)
        """
        # Validation du niveau
        Level = max(CompressionConfig.LEVEL_MIN, min(Level, CompressionConfig.LEVEL_MAX))
        self.Level = Level

        # Réinitialiser le compresseur zstd si actif pour appliquer le nouveau niveau
        if self.ZstdAvailable and self.Algorithm == self.ALGO_ZSTD:
            self._InitZstd()

        self.Logger.info(f"Niveau de compression configuré: {Level}/10 (natif: {self._ConvertToNativeLevel()})")

    def GetLevel(self) -> int:
        """
        Retourne le niveau de compression actuel (échelle commune 1-10)

        Returns:
            Niveau de compression
        """
        return self.Level

    def _ConvertToNativeLevel(self) -> int:
        """
        Convertit le niveau commun (1-10) vers le niveau natif de l'algorithme

        Returns:
            Niveau natif pour l'algorithme actuel
        """
        if self.Algorithm == self.ALGO_ZSTD:
            # 1-10 → 1-22 (interpolation linéaire)
            return round(1 + (self.Level - 1) * (CompressionConfig.ZSTD_LEVEL_MAX - 1) / (CompressionConfig.LEVEL_MAX - 1))
        elif self.Algorithm == self.ALGO_ZLIB:
            # 1-10 → 1-9 (cap à 9)
            return min(self.Level, CompressionConfig.ZLIB_LEVEL_MAX)
        return 0


def NegotiateCompression(ClientAlgorithms: List[str], ServerAlgorithms: List[str] = None) -> str:
    """
    Négocie le meilleur algorithme de compression commun

    Args:
        ClientAlgorithms: Algorithmes supportés par le client (par ordre de préférence)
        ServerAlgorithms: Algorithmes supportés par le serveur (optionnel)

    Returns:
        Algorithme sélectionné
    """
    if ServerAlgorithms is None:
        # Crée un handler temporaire pour obtenir les algos serveur
        Handler = CompressionHandler()
        ServerAlgorithms = Handler.GetSupportedAlgorithms()

    # Priorité: zstd > zlib > none
    Priority = [CompressionHandler.ALGO_ZSTD, CompressionHandler.ALGO_ZLIB, CompressionHandler.ALGO_NONE]

    for Algo in Priority:
        if Algo in ClientAlgorithms and Algo in ServerAlgorithms:
            return Algo

    # Fallback sur none si aucun algorithme commun
    return CompressionHandler.ALGO_NONE
