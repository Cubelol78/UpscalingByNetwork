"""
Cross-platform Real-ESRGAN handler
Supports Linux, Windows, and macOS with automatic executable detection
"""

import asyncio
import logging
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import time


class RealESRGANHandler:
    """Handle Real-ESRGAN operations in a cross-platform manner"""

    def __init__(
        self, executable_path: Optional[Path] = None, models_dir: Optional[Path] = None
    ):
        self.logger = logging.getLogger(__name__)

        # Detect executable
        self.executable_path = self._find_executable(executable_path)
        self.models_dir = self._find_models_directory(models_dir)

        # Configuration
        self.default_model = "RealESRGAN_x4plus"
        self.default_scale = 4
        self.default_tile_size = 256
        self.gpu_id = 0

        # Supported models
        self.supported_models = {
            "RealESRGAN_x4plus": {
                "name": "Real-ESRGAN x4 Plus",
                "scales": [4],
                "tile_size_recommend": 256,
            },
            "RealESRGAN_x4plus_anime_6B": {
                "name": "Real-ESRGAN x4 Plus Anime",
                "scales": [4],
                "tile_size_recommend": 256,
            },
            "realesr-animevideov3": {
                "name": "Real-ESRGAN Anime Video v3",
                "scales": [2, 3, 4],
                "tile_size_recommend": 128,
            },
            "RealESRNet_x4plus": {
                "name": "RealESRNet x4 Plus",
                "scales": [4],
                "tile_size_recommend": 256,
            },
        }

        # Statistics
        self.stats = {
            "total_images": 0,
            "total_time": 0.0,
            "avg_time_per_image": 0.0,
            "successful_batches": 0,
            "failed_batches": 0,
            "last_error": None,
        }

        # Verify Real-ESRGAN is available
        if not self._verify_executable():
            raise RuntimeError(
                f"Real-ESRGAN not available at {self.executable_path}"
            )

        self.logger.info(f"Real-ESRGAN initialized: {self.executable_path}")

    def _find_executable(self, custom_path: Optional[Path]) -> Path:
        """Find Real-ESRGAN executable for current platform"""
        if custom_path and custom_path.exists():
            return custom_path.resolve()

        # Determine executable name based on platform
        system = platform.system()
        if system == "Windows":
            exe_name = "realesrgan-ncnn-vulkan.exe"
        else:  # Linux, macOS
            exe_name = "realesrgan-ncnn-vulkan"

        # Search locations
        search_paths = [
            Path.cwd() / exe_name,
            Path.cwd() / "bin" / exe_name,
            Path.cwd() / "tools" / exe_name,
            Path(__file__).parent.parent.parent / "dependencies" / exe_name,
            Path(__file__).parent.parent / "dependencies" / exe_name,
            Path.home() / "tools" / exe_name,
            Path.home() / ".local" / "bin" / exe_name,
            Path("/usr/local/bin") / exe_name,
            Path("/usr/bin") / exe_name,
        ]

        # Check search paths
        for path in search_paths:
            if path.exists():
                self.logger.info(f"Found Real-ESRGAN at: {path}")
                return path.resolve()

        # Check system PATH
        system_path = shutil.which(exe_name)
        if system_path:
            self.logger.info(f"Found Real-ESRGAN in PATH: {system_path}")
            return Path(system_path)

        # Not found - return default name (will fail verification)
        self.logger.warning(f"Real-ESRGAN executable not found: {exe_name}")
        return Path(exe_name)

    def _find_models_directory(self, custom_dir: Optional[Path]) -> Path:
        """Find models directory"""
        if custom_dir and custom_dir.exists():
            return custom_dir.resolve()

        # Models are usually next to executable
        exe_dir = self.executable_path.parent

        candidates = [
            exe_dir / "models",
            exe_dir.parent / "models",
            exe_dir,
            Path.home() / ".local" / "share" / "upscaling-client" / "models",
        ]

        for candidate in candidates:
            if candidate.exists() and any(candidate.glob("*.bin")):
                self.logger.info(f"Found models directory: {candidate}")
                return candidate.resolve()

        # Default to models dir next to executable
        models_dir = exe_dir / "models"
        self.logger.warning(f"Models directory not found, using: {models_dir}")
        return models_dir

    def _verify_executable(self) -> bool:
        """Verify Real-ESRGAN executable is functional"""
        if not self.executable_path.exists():
            return False

        try:
            result = subprocess.run(
                [str(self.executable_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Real-ESRGAN returns error when run without args
            return "Usage:" in result.stderr or result.returncode != 0
        except Exception as e:
            self.logger.error(f"Error verifying Real-ESRGAN: {e}")
            return False

    async def upscale_image(
        self,
        input_path: Path,
        output_path: Path,
        model: Optional[str] = None,
        scale: Optional[int] = None,
        tile_size: Optional[int] = None,
        use_gpu: bool = True,
        tta_mode: bool = False,
    ) -> bool:
        """
        Upscale a single image

        Args:
            input_path: Input image path
            output_path: Output image path
            model: Model name to use
            scale: Upscaling scale factor
            tile_size: Tile size for processing
            use_gpu: Whether to use GPU
            tta_mode: Test-time augmentation mode

        Returns:
            True if successful
        """
        start_time = time.time()

        try:
            # Use defaults if not specified
            model = model or self.default_model
            scale = scale or self.default_scale
            tile_size = tile_size or self.default_tile_size

            # Validate input
            if not input_path.exists():
                raise FileNotFoundError(f"Input file not found: {input_path}")

            # Create output directory
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Build command
            cmd = [
                str(self.executable_path),
                "-i",
                str(input_path),
                "-o",
                str(output_path),
                "-n",
                model,
                "-s",
                str(scale),
                "-t",
                str(tile_size),
                "-f",
                "png",
            ]

            # GPU selection
            if use_gpu:
                cmd.extend(["-g", str(self.gpu_id)])
            else:
                cmd.extend(["-g", "-1"])  # CPU only

            # TTA mode
            if tta_mode:
                cmd.append("-x")

            self.logger.debug(f"Running: {' '.join(cmd)}")

            # Execute
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="ignore")
                raise RuntimeError(f"Real-ESRGAN failed: {error_msg}")

            # Verify output
            if not output_path.exists():
                raise RuntimeError("Output file not created")

            # Update stats
            processing_time = time.time() - start_time
            self._update_stats(processing_time, True)

            self.logger.debug(
                f"Image upscaled in {processing_time:.2f}s: {input_path.name}"
            )
            return True

        except Exception as e:
            processing_time = time.time() - start_time
            self._update_stats(processing_time, False)
            self.stats["last_error"] = str(e)
            self.logger.error(f"Error upscaling {input_path}: {e}")
            return False

    async def upscale_batch(
        self,
        input_dir: Path,
        output_dir: Path,
        model: Optional[str] = None,
        scale: Optional[int] = None,
        tile_size: Optional[int] = None,
        use_gpu: bool = True,
        tta_mode: bool = False,
        progress_callback: Optional[Callable[[float, int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Upscale a batch of images

        Args:
            input_dir: Input directory with images
            output_dir: Output directory
            model: Model name
            scale: Upscaling scale
            tile_size: Tile size
            use_gpu: Use GPU
            tta_mode: TTA mode
            progress_callback: Progress callback(progress, current, total)

        Returns:
            Dictionary with results
        """
        start_time = time.time()

        try:
            if not input_dir.exists():
                raise FileNotFoundError(f"Input directory not found: {input_dir}")

            output_dir.mkdir(parents=True, exist_ok=True)

            # Find images
            image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
            image_files = []

            for ext in image_extensions:
                image_files.extend(input_dir.glob(f"*{ext}"))
                image_files.extend(input_dir.glob(f"*{ext.upper()}"))

            image_files = sorted(set(image_files))

            if not image_files:
                raise ValueError(f"No images found in {input_dir}")

            self.logger.info(f"Processing {len(image_files)} images")

            # Process images
            results = {
                "total_images": len(image_files),
                "processed_images": 0,
                "failed_images": 0,
                "processing_time": 0.0,
                "failed_files": [],
                "success": False,
            }

            for i, image_path in enumerate(image_files):
                try:
                    output_path = output_dir / f"{image_path.stem}.png"

                    success = await self.upscale_image(
                        image_path,
                        output_path,
                        model,
                        scale,
                        tile_size,
                        use_gpu,
                        tta_mode,
                    )

                    if success:
                        results["processed_images"] += 1
                    else:
                        results["failed_images"] += 1
                        results["failed_files"].append(str(image_path))

                    # Progress callback
                    if progress_callback:
                        progress = (i + 1) / len(image_files)
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback(progress, i + 1, len(image_files))
                        else:
                            progress_callback(progress, i + 1, len(image_files))

                except Exception as e:
                    self.logger.error(f"Error processing {image_path}: {e}")
                    results["failed_images"] += 1
                    results["failed_files"].append(str(image_path))

            # Finalize results
            results["processing_time"] = time.time() - start_time
            results["success"] = results["failed_images"] == 0

            if results["success"]:
                self.stats["successful_batches"] += 1
            else:
                self.stats["failed_batches"] += 1

            self.logger.info(
                f"Batch complete: {results['processed_images']}/{results['total_images']} "
                f"in {results['processing_time']:.1f}s"
            )

            return results

        except Exception as e:
            self.logger.error(f"Error processing batch: {e}")
            self.stats["failed_batches"] += 1
            return {
                "total_images": 0,
                "processed_images": 0,
                "failed_images": 0,
                "processing_time": time.time() - start_time,
                "failed_files": [],
                "success": False,
                "error": str(e),
            }

    def _update_stats(self, processing_time: float, success: bool):
        """Update processing statistics"""
        if success:
            self.stats["total_images"] += 1
            self.stats["total_time"] += processing_time

            if self.stats["total_images"] > 0:
                self.stats["avg_time_per_image"] = (
                    self.stats["total_time"] / self.stats["total_images"]
                )

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            **self.stats,
            "executable_path": str(self.executable_path),
            "models_dir": str(self.models_dir),
            "available_models": self.list_available_models(),
        }

    def list_available_models(self) -> List[str]:
        """List available models"""
        if not self.models_dir.exists():
            return []

        available = []
        for model_name in self.supported_models.keys():
            bin_file = self.models_dir / f"{model_name}.bin"
            param_file = self.models_dir / f"{model_name}.param"

            if bin_file.exists() and param_file.exists():
                available.append(model_name)

        return available

    def test_installation(self) -> Dict[str, Any]:
        """Test Real-ESRGAN installation"""
        result = {
            "executable_found": self.executable_path.exists(),
            "executable_path": str(self.executable_path),
            "models_dir": str(self.models_dir),
            "models_found": self.list_available_models(),
            "functional": False,
            "error": None,
        }

        try:
            result["functional"] = self._verify_executable()
        except Exception as e:
            result["error"] = str(e)

        return result
