"""
Image processor for the distributed upscaling client
Handles batch processing with Real-ESRGAN
"""

import asyncio
import logging
import shutil
import time
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional, List
import io


class ClientProcessor:
    """Process image batches with Real-ESRGAN"""

    def __init__(self, client, realesrgan_handler, security, config):
        self.client = client
        self.realesrgan = realesrgan_handler
        self.security = security
        self.config = config
        self.logger = logging.getLogger(__name__)

        # State
        self.is_processing = False
        self.current_batch_id = None
        self.processing_start_time = None

        # Directories
        self.work_dir = config.get_work_directory()
        self.temp_dir = config.get_temp_directory()
        self.input_dir = self.work_dir / "input"
        self.output_dir = self.work_dir / "output"

        for directory in [self.input_dir, self.output_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        # Statistics
        self.stats = {
            "batches_processed": 0,
            "total_frames_processed": 0,
            "total_processing_time": 0.0,
            "average_time_per_frame": 0.0,
            "errors_count": 0,
            "last_error": None,
            "data_received_mb": 0.0,
            "data_sent_mb": 0.0,
        }

    async def process_batch(
        self, batch_data: bytes, batch_id: str, batch_config: Dict[str, Any]
    ) -> Optional[bytes]:
        """
        Process a batch of images

        Args:
            batch_data: Encrypted batch data
            batch_id: Batch identifier
            batch_config: Processing configuration

        Returns:
            Encrypted result data or None on error
        """
        if self.is_processing:
            self.logger.warning(f"Already processing batch {self.current_batch_id}")
            return None

        self.is_processing = True
        self.current_batch_id = batch_id
        self.processing_start_time = time.time()

        try:
            self.logger.info(f"Processing batch {batch_id}")

            # Decrypt data
            decrypted_data = self.security.decrypt_data(batch_data)
            if decrypted_data is None:
                raise Exception("Decryption failed")

            self.stats["data_received_mb"] += len(batch_data) / (1024 * 1024)

            # Setup directories
            batch_input_dir = self.input_dir / batch_id
            batch_output_dir = self.output_dir / batch_id

            if batch_input_dir.exists():
                shutil.rmtree(batch_input_dir)
            if batch_output_dir.exists():
                shutil.rmtree(batch_output_dir)

            batch_input_dir.mkdir(parents=True)
            batch_output_dir.mkdir(parents=True)

            # Extract ZIP
            zip_path = self.temp_dir / f"{batch_id}.zip"
            with open(zip_path, "wb") as f:
                f.write(decrypted_data)

            extracted_files = self._extract_zip(zip_path, batch_input_dir)
            if not extracted_files:
                raise Exception("No files extracted")

            self.logger.info(f"Extracted {len(extracted_files)} images")

            # Process with Real-ESRGAN
            model = batch_config.get("model", self.config.get("processing.realesrgan_model"))
            scale = batch_config.get("scale", self.config.get("processing.scale"))
            tile_size = batch_config.get("tile_size", self.config.get("processing.tile_size"))
            use_gpu = batch_config.get("use_gpu", self.config.get("processing.use_gpu"))
            tta_mode = batch_config.get("tta_mode", self.config.get("processing.tta_mode"))

            result = await self.realesrgan.upscale_batch(
                batch_input_dir,
                batch_output_dir,
                model=model,
                scale=scale,
                tile_size=tile_size,
                use_gpu=use_gpu,
                tta_mode=tta_mode,
            )

            if not result["success"]:
                raise Exception("Processing failed")

            self.logger.info(
                f"Processed {result['processed_images']} images "
                f"in {result['processing_time']:.1f}s"
            )

            # Create result ZIP
            result_zip_path = self.temp_dir / f"{batch_id}_result.zip"
            self._create_zip(batch_output_dir, result_zip_path)

            # Encrypt result
            with open(result_zip_path, "rb") as f:
                result_data = f.read()

            encrypted_result = self.security.encrypt_data(result_data)
            if encrypted_result is None:
                raise Exception("Encryption failed")

            self.stats["data_sent_mb"] += len(encrypted_result) / (1024 * 1024)

            # Cleanup
            self._cleanup_batch(
                batch_id, zip_path, result_zip_path, batch_input_dir, batch_output_dir
            )

            # Update stats
            processing_time = time.time() - self.processing_start_time
            self.stats["batches_processed"] += 1
            self.stats["total_frames_processed"] += result["processed_images"]
            self.stats["total_processing_time"] += processing_time

            if self.stats["total_frames_processed"] > 0:
                self.stats["average_time_per_frame"] = (
                    self.stats["total_processing_time"]
                    / self.stats["total_frames_processed"]
                )

            return encrypted_result

        except Exception as e:
            self.logger.error(f"Error processing batch {batch_id}: {e}")
            self.stats["errors_count"] += 1
            self.stats["last_error"] = str(e)

            try:
                self._cleanup_batch(batch_id)
            except:
                pass

            return None

        finally:
            self.is_processing = False
            self.current_batch_id = None
            self.processing_start_time = None

    def _extract_zip(self, zip_path: Path, extract_dir: Path) -> List[str]:
        """Extract ZIP file"""
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Security check
                for name in zf.namelist():
                    if ".." in name or name.startswith("/"):
                        raise Exception(f"Unsafe filename: {name}")

                zf.extractall(extract_dir)
                extracted_files = zf.namelist()

            # Filter image files
            image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
            image_files = [
                f
                for f in extracted_files
                if Path(f).suffix.lower() in image_extensions
            ]

            return image_files

        except Exception as e:
            self.logger.error(f"Error extracting ZIP: {e}")
            return []

    def _create_zip(self, source_dir: Path, zip_path: Path):
        """Create ZIP file"""
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                for file_path in source_dir.glob("*"):
                    if file_path.is_file():
                        zf.write(file_path, file_path.name)

            self.logger.debug(f"Created ZIP: {zip_path}")

        except Exception as e:
            self.logger.error(f"Error creating ZIP: {e}")
            raise

    def _cleanup_batch(self, batch_id: str, *additional_paths):
        """Cleanup batch files"""
        try:
            batch_input_dir = self.input_dir / batch_id
            batch_output_dir = self.output_dir / batch_id

            for directory in [batch_input_dir, batch_output_dir]:
                if directory.exists():
                    shutil.rmtree(directory)

            for path in additional_paths:
                if path and Path(path).exists():
                    Path(path).unlink()

            self.logger.debug(f"Cleaned up batch {batch_id}")

        except Exception as e:
            self.logger.error(f"Error cleaning up batch {batch_id}: {e}")

    def cleanup_old_files(self, max_age_hours: int = 24):
        """Cleanup old temporary files"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            cleaned_count = 0

            for directory in [self.temp_dir, self.input_dir, self.output_dir]:
                if not directory.exists():
                    continue

                for item in directory.iterdir():
                    try:
                        if current_time - item.stat().st_mtime > max_age_seconds:
                            if item.is_file():
                                item.unlink()
                            elif item.is_dir():
                                shutil.rmtree(item)
                            cleaned_count += 1
                    except Exception as e:
                        self.logger.warning(f"Cannot delete {item}: {e}")

            if cleaned_count > 0:
                self.logger.info(f"Cleaned up {cleaned_count} old items")

        except Exception as e:
            self.logger.error(f"Error cleaning old files: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics"""
        return {
            "processing_state": {
                "is_processing": self.is_processing,
                "current_batch_id": self.current_batch_id,
                "processing_duration": (
                    time.time() - self.processing_start_time
                    if self.processing_start_time
                    else 0
                ),
            },
            "performance_stats": self.stats.copy(),
        }

    def get_capabilities(self) -> Dict[str, Any]:
        """Get processing capabilities"""
        realesrgan_test = self.realesrgan.test_installation()

        return {
            "realesrgan_available": realesrgan_test["functional"],
            "models_available": realesrgan_test["models_found"],
            "gpu_support": self.config.get("processing.use_gpu"),
        }
