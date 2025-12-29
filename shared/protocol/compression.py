"""
Module de compression pour les transferts réseau
Supporte zstd (prioritaire) avec fallback sur zlib
"""

import zlib
from typing import List, Optional

from shared.utils.logger import GetModuleLogger


class CompressionHandler:
    """Gestionnaire de compression avec support zstd et fallback zlib"""

    ALGO_NONE = "none"
    ALGO_ZSTD = "zstd"
    ALGO_ZLIB = "zlib"

    # Niveaux de compression par défaut
    ZSTD_LEVEL = 3   # zstd: 1-22, 3 = bon équilibre vitesse/compression
    ZLIB_LEVEL = 6   # zlib: 1-9, 6 = défaut Python

    def __init__(self):
        """Initialise le gestionnaire de compression"""
        self.Logger = GetModuleLogger("CompressionHandler")
        self.Algorithm = self.ALGO_NONE
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
            self.ZstdCompressor = zstd.ZstdCompressor(level=self.ZSTD_LEVEL)
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
            self.Logger.error(f"Erreur de compression: {e}")
            return Data

    def Decompress(self, Data: bytes) -> bytes:
        """
        Décompresse les données selon l'algorithme configuré

        Args:
            Data: Données compressées

        Returns:
            Données décompressées
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
            self.Logger.error(f"Erreur de décompression: {e}")
            raise

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
        return zlib.compress(Data, level=self.ZLIB_LEVEL)

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
