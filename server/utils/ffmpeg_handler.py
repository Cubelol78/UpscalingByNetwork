"""
Gestionnaire FFmpeg pour le traitement vidéo
Utilise imageio-ffmpeg pour la portabilité
"""

import os
import subprocess
import json
import re
from typing import Optional, List, Dict, Tuple
from pathlib import Path

from shared.utils.logger import GetModuleLogger


class FFmpegHandler:
    """Gestionnaire FFmpeg pour extraction et assemblage vidéo"""

    def __init__(self):
        """Initialise le gestionnaire FFmpeg"""
        self.Logger = GetModuleLogger("FFmpegHandler")
        self.FfmpegPath = None
        self.FfprobePath = None

        # Détecte les binaires FFmpeg
        self._DetectFfmpegBinaries()

    def _DetectFfmpegBinaries(self):
        """Détecte les binaires FFmpeg (imageio-ffmpeg)"""
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            self.FfmpegPath = get_ffmpeg_exe()

            # Dérive ffprobe depuis ffmpeg (si disponible)
            FfmpegDir = os.path.dirname(self.FfmpegPath)
            if os.name == 'nt':  # Windows
                FfprobePath = os.path.join(FfmpegDir, 'ffprobe.exe')
            else:  # Linux/Mac
                FfprobePath = os.path.join(FfmpegDir, 'ffprobe')

            # Vérifie que ffprobe existe
            if os.path.exists(FfprobePath):
                self.FfprobePath = FfprobePath
                self.Logger.info(f"FFprobe détecté: {self.FfprobePath}")
            else:
                # Essaie la commande système
                try:
                    subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
                    self.FfprobePath = 'ffprobe'
                    self.Logger.info("FFprobe système détecté")
                except (subprocess.CalledProcessError, FileNotFoundError):
                    self.FfprobePath = None
                    self.Logger.warning("FFprobe non disponible - utilisation de FFmpeg pour les métadonnées")

            self.Logger.info(f"FFmpeg détecté: {self.FfmpegPath}")

        except Exception as e:
            self.Logger.error(f"Impossible de détecter FFmpeg: {e}")
            raise

    def ExtractFramerate(self, VideoPath: str) -> Optional[float]:
        """
        Extrait le framerate d'une vidéo

        Args:
            VideoPath: Chemin vers la vidéo

        Returns:
            Framerate (fps) ou None si erreur
        """
        try:
            # Utilise ffprobe si disponible
            if self.FfprobePath:
                Command = [
                    self.FfprobePath,
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=r_frame_rate',
                    '-of', 'json',
                    VideoPath
                ]

                Result = subprocess.run(
                    Command,
                    capture_output=True,
                    text=True,
                    check=True
                )

                Data = json.loads(Result.stdout)
                FrameRateStr = Data['streams'][0]['r_frame_rate']

                # Parse la fraction (ex: "30000/1001" ou "30/1")
                Num, Den = map(int, FrameRateStr.split('/'))
                Fps = Num / Den
            else:
                # Fallback: utilise ffmpeg -i et parse stderr
                Fps = self._ExtractFramerateWithFfmpeg(VideoPath)

            if Fps:
                self.Logger.info(f"Framerate extrait: {Fps:.2f} fps")
            return Fps

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'extraction du framerate: {e}")
            # Fallback si ffprobe échoue
            try:
                return self._ExtractFramerateWithFfmpeg(VideoPath)
            except Exception:
                return None

    def _ExtractFramerateWithFfmpeg(self, VideoPath: str) -> Optional[float]:
        """Extrait le framerate en utilisant ffmpeg -i"""
        Command = [self.FfmpegPath, '-i', VideoPath]
        Result = subprocess.run(Command, capture_output=True, text=True)

        # Parse stderr pour trouver le framerate
        # Format typique: "25 fps" ou "29.97 fps" ou "30 tbr"
        Output = Result.stderr

        # Cherche le pattern fps
        FpsMatch = re.search(r'(\d+(?:\.\d+)?)\s*fps', Output)
        if FpsMatch:
            return float(FpsMatch.group(1))

        # Cherche le pattern tbr (time base rate)
        TbrMatch = re.search(r'(\d+(?:\.\d+)?)\s*tbr', Output)
        if TbrMatch:
            return float(TbrMatch.group(1))

        return None

    def ExtractVideoMetadata(self, VideoPath: str) -> Optional[Dict]:
        """
        Extrait les métadonnées complètes d'une vidéo

        Args:
            VideoPath: Chemin vers la vidéo

        Returns:
            Dictionnaire de métadonnées ou None
        """
        try:
            # Utilise ffprobe si disponible
            if self.FfprobePath:
                Command = [
                    self.FfprobePath,
                    '-v', 'error',
                    '-show_format',
                    '-show_streams',
                    '-of', 'json',
                    VideoPath
                ]

                Result = subprocess.run(
                    Command,
                    capture_output=True,
                    text=True,
                    check=True
                )

                Metadata = json.loads(Result.stdout)
            else:
                # Fallback: utilise ffmpeg -i et parse stderr
                Metadata = self._ExtractMetadataWithFfmpeg(VideoPath)

            if Metadata:
                self.Logger.info(f"Métadonnées extraites de {os.path.basename(VideoPath)}")
            return Metadata

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'extraction des métadonnées: {e}")
            # Fallback si ffprobe échoue
            try:
                return self._ExtractMetadataWithFfmpeg(VideoPath)
            except Exception:
                return None

    def _ExtractMetadataWithFfmpeg(self, VideoPath: str) -> Optional[Dict]:
        """Extrait les métadonnées en utilisant ffmpeg -i"""
        Command = [self.FfmpegPath, '-i', VideoPath]
        Result = subprocess.run(Command, capture_output=True, text=True)
        Output = Result.stderr

        Metadata = {
            'format': {},
            'streams': []
        }

        # Parse la durée
        DurationMatch = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', Output)
        if DurationMatch:
            Hours, Minutes, Seconds = DurationMatch.groups()
            TotalSeconds = int(Hours) * 3600 + int(Minutes) * 60 + float(Seconds)
            Metadata['format']['duration'] = str(TotalSeconds)

        # Parse le bitrate global
        BitrateMatch = re.search(r'bitrate:\s*(\d+)\s*kb/s', Output)
        if BitrateMatch:
            Metadata['format']['bit_rate'] = str(int(BitrateMatch.group(1)) * 1000)

        # Parse les streams vidéo
        VideoMatch = re.search(
            r'Stream #\d+:\d+.*Video:\s*(\w+)[^,]*,\s*(\w+)[^,]*,\s*(\d+)x(\d+).*?(\d+(?:\.\d+)?)\s*fps',
            Output
        )
        if VideoMatch:
            Codec, PixFmt, Width, Height, Fps = VideoMatch.groups()
            Metadata['streams'].append({
                'codec_type': 'video',
                'codec_name': Codec,
                'pix_fmt': PixFmt,
                'width': int(Width),
                'height': int(Height),
                'r_frame_rate': f"{Fps}/1"
            })

        # Parse les streams audio
        AudioMatches = re.finditer(
            r'Stream #\d+:(\d+).*Audio:\s*(\w+)[^,]*,\s*(\d+)\s*Hz',
            Output
        )
        for Match in AudioMatches:
            StreamIdx, Codec, SampleRate = Match.groups()
            Metadata['streams'].append({
                'codec_type': 'audio',
                'codec_name': Codec,
                'sample_rate': SampleRate,
                'index': int(StreamIdx)
            })

        # Parse les streams de sous-titres
        SubMatches = re.finditer(
            r'Stream #\d+:(\d+).*Subtitle:\s*(\w+)',
            Output
        )
        for Match in SubMatches:
            StreamIdx, Codec = Match.groups()
            Metadata['streams'].append({
                'codec_type': 'subtitle',
                'codec_name': Codec,
                'index': int(StreamIdx)
            })

        return Metadata if Metadata['streams'] else None

    def GetTotalFrames(self, VideoPath: str) -> Optional[int]:
        """
        Récupère le nombre total de frames

        Args:
            VideoPath: Chemin vers la vidéo

        Returns:
            Nombre de frames ou None
        """
        try:
            # Utilise ffprobe si disponible
            if self.FfprobePath:
                Command = [
                    self.FfprobePath,
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-count_frames',
                    '-show_entries', 'stream=nb_read_frames',
                    '-of', 'json',
                    VideoPath
                ]

                Result = subprocess.run(
                    Command,
                    capture_output=True,
                    text=True,
                    check=True
                )

                Data = json.loads(Result.stdout)

                if 'streams' in Data and len(Data['streams']) > 0:
                    Frames = int(Data['streams'][0].get('nb_read_frames', 0))
                    self.Logger.info(f"Nombre total de frames: {Frames}")
                    return Frames
            else:
                # Fallback: calcule à partir de la durée et du framerate
                Frames = self._GetTotalFramesWithFfmpeg(VideoPath)
                if Frames:
                    self.Logger.info(f"Nombre total de frames (estimé): {Frames}")
                    return Frames

            return None

        except Exception as e:
            self.Logger.error(f"Erreur lors du comptage des frames: {e}")
            # Fallback
            try:
                return self._GetTotalFramesWithFfmpeg(VideoPath)
            except Exception:
                return None

    def _GetTotalFramesWithFfmpeg(self, VideoPath: str) -> Optional[int]:
        """Estime le nombre de frames en utilisant durée * framerate"""
        Metadata = self._ExtractMetadataWithFfmpeg(VideoPath)
        if not Metadata:
            return None

        # Récupère la durée
        Duration = float(Metadata.get('format', {}).get('duration', 0))
        if not Duration:
            return None

        # Récupère le framerate
        Fps = self._ExtractFramerateWithFfmpeg(VideoPath)
        if not Fps:
            return None

        return int(Duration * Fps)

    def ExtractAudioTracks(self, VideoPath: str, OutputDir: str) -> List[str]:
        """
        Extrait toutes les pistes audio d'une vidéo

        Args:
            VideoPath: Chemin vers la vidéo
            OutputDir: Répertoire de sortie

        Returns:
            Liste des chemins vers les pistes audio extraites
        """
        try:
            os.makedirs(OutputDir, exist_ok=True)

            # Récupère le nombre de pistes audio
            Metadata = self.ExtractVideoMetadata(VideoPath)
            if not Metadata:
                return []

            AudioTracks = []
            TrackIndex = 0

            for Stream in Metadata.get('streams', []):
                if Stream.get('codec_type') == 'audio':
                    OutputPath = os.path.join(OutputDir, f'audio_track_{TrackIndex}.aac')

                    Command = [
                        self.FfmpegPath,
                        '-i', VideoPath,
                        '-map', f'0:a:{TrackIndex}',
                        '-c:a', 'copy',
                        '-y',
                        OutputPath
                    ]

                    subprocess.run(Command, capture_output=True, check=True)
                    AudioTracks.append(OutputPath)
                    self.Logger.info(f"Piste audio {TrackIndex} extraite: {OutputPath}")
                    TrackIndex += 1

            return AudioTracks

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'extraction des pistes audio: {e}")
            return []

    def ExtractSubtitles(self, VideoPath: str, OutputDir: str) -> List[str]:
        """
        Extrait tous les sous-titres d'une vidéo

        Args:
            VideoPath: Chemin vers la vidéo
            OutputDir: Répertoire de sortie

        Returns:
            Liste des chemins vers les sous-titres extraits
        """
        try:
            os.makedirs(OutputDir, exist_ok=True)

            # Récupère le nombre de pistes de sous-titres
            Metadata = self.ExtractVideoMetadata(VideoPath)
            if not Metadata:
                return []

            Subtitles = []
            SubIndex = 0

            for Stream in Metadata.get('streams', []):
                if Stream.get('codec_type') == 'subtitle':
                    CodecName = Stream.get('codec_name', 'srt')
                    Extension = 'srt' if CodecName == 'subrip' else CodecName
                    OutputPath = os.path.join(OutputDir, f'subtitle_{SubIndex}.{Extension}')

                    Command = [
                        self.FfmpegPath,
                        '-i', VideoPath,
                        '-map', f'0:s:{SubIndex}',
                        '-c:s', 'copy',
                        '-y',
                        OutputPath
                    ]

                    subprocess.run(Command, capture_output=True, check=True)
                    Subtitles.append(OutputPath)
                    self.Logger.info(f"Sous-titre {SubIndex} extrait: {OutputPath}")
                    SubIndex += 1

            return Subtitles

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'extraction des sous-titres: {e}")
            return []

    def VideoToFrames(self, VideoPath: str, OutputDir: str, Quality: int = 2) -> bool:
        """
        Découpe une vidéo en images individuelles

        Args:
            VideoPath: Chemin vers la vidéo
            OutputDir: Répertoire de sortie
            Quality: Qualité JPEG (1-31, 1=meilleur, 31=pire)

        Returns:
            True si succès
        """
        try:
            os.makedirs(OutputDir, exist_ok=True)

            # Nom du pattern pour les images
            OutputPattern = os.path.join(OutputDir, 'frame_%08d.png')

            Command = [
                self.FfmpegPath,
                '-i', VideoPath,
                '-qscale:v', str(Quality),
                '-start_number', '0',
                OutputPattern
            ]

            self.Logger.info(f"Découpage de la vidéo en images...")
            Result = subprocess.run(Command, capture_output=True, text=True)

            if Result.returncode == 0:
                # Compte le nombre d'images créées
                FrameCount = len([f for f in os.listdir(OutputDir) if f.endswith('.png')])
                self.Logger.info(f"✓ {FrameCount} images extraites dans {OutputDir}")
                return True
            else:
                self.Logger.error(f"Erreur FFmpeg: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors du découpage en images: {e}")
            return False

    def FramesToVideo(self, FramesDir: str, OutputPath: str, Fps: float,
                     Quality: int = 18) -> bool:
        """
        Réassemble des images en vidéo

        Args:
            FramesDir: Répertoire contenant les images
            OutputPath: Chemin de la vidéo de sortie
            Fps: Framerate de la vidéo
            Quality: CRF pour x264 (0-51, 18=défaut)

        Returns:
            True si succès
        """
        try:
            # Pattern pour les images
            InputPattern = os.path.join(FramesDir, 'frame_%08d.png')

            Command = [
                self.FfmpegPath,
                '-framerate', str(Fps),
                '-i', InputPattern,
                '-c:v', 'libx264',
                '-crf', str(Quality),
                '-preset', 'medium',
                '-pix_fmt', 'yuv420p',
                '-y',
                OutputPath
            ]

            self.Logger.info(f"Réassemblage des images en vidéo...")
            Result = subprocess.run(Command, capture_output=True, text=True)

            if Result.returncode == 0:
                self.Logger.info(f"✓ Vidéo créée: {OutputPath}")
                return True
            else:
                self.Logger.error(f"Erreur FFmpeg: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors du réassemblage: {e}")
            return False

    def MergeAudioSubtitles(self, VideoPath: str, AudioTracks: List[str],
                           Subtitles: List[str], OutputPath: str) -> bool:
        """
        Réintègre les pistes audio et sous-titres dans une vidéo

        Args:
            VideoPath: Chemin vers la vidéo (sans audio/sous-titres)
            AudioTracks: Liste des pistes audio
            Subtitles: Liste des sous-titres
            OutputPath: Chemin de sortie

        Returns:
            True si succès
        """
        try:
            Command = [self.FfmpegPath, '-i', VideoPath]

            # Ajoute les pistes audio
            for AudioTrack in AudioTracks:
                Command.extend(['-i', AudioTrack])

            # Ajoute les sous-titres
            for Subtitle in Subtitles:
                Command.extend(['-i', Subtitle])

            # Map la vidéo
            Command.extend(['-map', '0:v:0'])

            # Map toutes les pistes audio
            for i in range(len(AudioTracks)):
                Command.extend(['-map', f'{i+1}:a:0'])

            # Map tous les sous-titres
            for i in range(len(Subtitles)):
                Command.extend(['-map', f'{i+1+len(AudioTracks)}:s:0'])

            # Options de copie
            Command.extend([
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-c:s', 'copy',
                '-y',
                OutputPath
            ])

            self.Logger.info(f"Réintégration audio/sous-titres...")
            Result = subprocess.run(Command, capture_output=True, text=True)

            if Result.returncode == 0:
                self.Logger.info(f"✓ Audio/sous-titres réintégrés: {OutputPath}")
                return True
            else:
                self.Logger.error(f"Erreur FFmpeg: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors de la réintégration: {e}")
            return False

    def EncodeToAV1(self, InputPath: str, OutputPath: str, Crf: int = 35) -> bool:
        """
        Encode une vidéo en AV1

        Args:
            InputPath: Chemin de la vidéo d'entrée
            OutputPath: Chemin de sortie
            Crf: Qualité (0-63, 35=défaut, plus élevé=plus compressé)

        Returns:
            True si succès
        """
        try:
            Command = [
                self.FfmpegPath,
                '-i', InputPath,
                '-c:v', 'libaom-av1',
                '-crf', str(Crf),
                '-b:v', '0',
                '-c:a', 'copy',
                '-c:s', 'copy',
                '-strict', 'experimental',
                '-y',
                OutputPath
            ]

            self.Logger.info(f"Encodage en AV1 (CRF={Crf})...")
            self.Logger.warning("⚠ L'encodage AV1 peut être très lent!")

            Result = subprocess.run(Command, capture_output=True, text=True)

            if Result.returncode == 0:
                self.Logger.info(f"✓ Vidéo encodée en AV1: {OutputPath}")
                return True
            else:
                self.Logger.error(f"Erreur FFmpeg: {Result.stderr}")
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'encodage AV1: {e}")
            return False

    def GetVideoDuration(self, VideoPath: str) -> Optional[float]:
        """
        Récupère la durée d'une vidéo en secondes

        Args:
            VideoPath: Chemin vers la vidéo

        Returns:
            Durée en secondes ou None
        """
        try:
            Metadata = self.ExtractVideoMetadata(VideoPath)
            if Metadata and 'format' in Metadata:
                Duration = float(Metadata['format'].get('duration', 0))
                self.Logger.info(f"Durée: {Duration:.2f}s")
                return Duration
            return None

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'extraction de la durée: {e}")
            return None


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    # Test du gestionnaire FFmpeg
    Handler = FFmpegHandler()

    print("\n=== Test FFmpegHandler ===")
    print(f"FFmpeg: {Handler.FfmpegPath}")
    print(f"FFprobe: {Handler.FfprobePath}")

    # Test avec une vidéo (si disponible)
    TestVideo = "test.mp4"
    if os.path.exists(TestVideo):
        print(f"\nTest avec {TestVideo}")

        Fps = Handler.ExtractFramerate(TestVideo)
        print(f"Framerate: {Fps} fps")

        Duration = Handler.GetVideoDuration(TestVideo)
        print(f"Durée: {Duration}s")

        Frames = Handler.GetTotalFrames(TestVideo)
        print(f"Frames: {Frames}")
    else:
        print(f"\n⚠ Fichier de test {TestVideo} non trouvé")
