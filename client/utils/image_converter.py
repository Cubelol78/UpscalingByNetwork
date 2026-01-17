"""
Convertisseur d'images pour optimisation des transferts réseau
Supporte la conversion PNG -> AVIF après l'upscaling Real-ESRGAN
"""

import os
import io
from typing import Tuple
from PIL import Image
from shared.utils.logger import GetModuleLogger


class ImageConverter:
    """Convertisseur d'images pour réduction de taille des transferts"""

    FORMAT_PNG = "png"
    FORMAT_AVIF = "avif"
    FORMAT_WEBP = "webp"

    SUPPORTED_FORMATS = [FORMAT_PNG, FORMAT_AVIF, FORMAT_WEBP]

    DEFAULT_QUALITY = 95
    LOSSLESS_QUALITY = 100

    def __init__(self):
        self.Logger = GetModuleLogger("ImageConverter")
        self._AvifSupported = self._CheckAvifSupport()

    def _CheckAvifSupport(self) -> bool:
        """Vérifie si le support AVIF est disponible"""
        try:
            import pillow_heif
            pillow_heif.register_avif_opener()
            self.Logger.info("Support AVIF via pillow-heif actif")
            return True
        except ImportError:
            pass

        try:
            Test = Image.new('RGB', (10, 10))
            Buffer = io.BytesIO()
            Test.save(Buffer, format='AVIF')
            self.Logger.info("Support AVIF natif Pillow actif")
            return True
        except Exception:
            pass

        self.Logger.warning("Support AVIF non disponible, fallback PNG")
        return False

    def IsAvifSupported(self) -> bool:
        """Retourne True si AVIF est supporté"""
        return self._AvifSupported

    def ConvertToFormat(self, InputPath: str, OutputFormat: str,
                        Quality: int = DEFAULT_QUALITY,
                        Lossless: bool = False) -> Tuple[bytes, str]:
        """
        Convertit une image vers le format spécifié

        Args:
            InputPath: Chemin de l'image source (PNG)
            OutputFormat: Format cible (png, avif, webp)
            Quality: Qualité (1-100) pour formats lossy
            Lossless: Si True, utilise compression lossless

        Returns:
            Tuple (ImageBytes, Extension)
        """
        try:
            with Image.open(InputPath) as Img:
                Buffer = io.BytesIO()

                if OutputFormat == self.FORMAT_AVIF:
                    if not self._AvifSupported:
                        self.Logger.debug("AVIF non supporté, fallback PNG")
                        OutputFormat = self.FORMAT_PNG
                    else:
                        SaveKwargs = {'format': 'AVIF'}
                        if Lossless:
                            SaveKwargs['quality'] = -1
                        else:
                            SaveKwargs['quality'] = Quality
                        Img.save(Buffer, **SaveKwargs)
                        return Buffer.getvalue(), '.avif'

                if OutputFormat == self.FORMAT_WEBP:
                    SaveKwargs = {'format': 'WEBP', 'quality': Quality}
                    if Lossless:
                        SaveKwargs['lossless'] = True
                    Img.save(Buffer, **SaveKwargs)
                    return Buffer.getvalue(), '.webp'

                Img.save(Buffer, format='PNG', optimize=True)
                return Buffer.getvalue(), '.png'

        except Exception as e:
            self.Logger.error(f"Erreur conversion {InputPath}: {e}")
            with open(InputPath, 'rb') as f:
                return f.read(), os.path.splitext(InputPath)[1]

    def GetOptimalFormat(self) -> str:
        """Retourne le format optimal disponible"""
        if self._AvifSupported:
            return self.FORMAT_AVIF
        return self.FORMAT_PNG
