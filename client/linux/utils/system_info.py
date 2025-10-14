"""
Cross-platform system information collector
Linux-compatible with pynvml for GPU detection
"""

import platform
import psutil
import subprocess
import logging
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path


class SystemInfo:
    """Collect system information in a cross-platform manner"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._static_info_cache = None
        self._gpu_info_cache = None

    def get_system_info(self) -> Dict[str, Any]:
        """Get complete system information"""
        return {
            "basic": self._get_basic_info(),
            "hardware": self._get_hardware_info(),
            "performance": self._get_performance_info(),
            "vulkan": self._get_vulkan_info(),
        }

    def _get_basic_info(self) -> Dict[str, Any]:
        """Get basic system information"""
        try:
            return {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "hostname": platform.node(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
            }
        except Exception as e:
            self.logger.error(f"Error getting basic info: {e}")
            return {"platform": "Unknown"}

    def _get_hardware_info(self) -> Dict[str, Any]:
        """Get hardware information"""
        try:
            cpu_freq = psutil.cpu_freq()

            return {
                "cpu": {
                    "physical_cores": psutil.cpu_count(logical=False),
                    "logical_cores": psutil.cpu_count(logical=True),
                    "max_frequency_mhz": cpu_freq.max if cpu_freq else 0,
                    "current_frequency_mhz": cpu_freq.current if cpu_freq else 0,
                },
                "memory": {
                    "total_bytes": psutil.virtual_memory().total,
                    "total_ram_gb": round(
                        psutil.virtual_memory().total / (1024**3), 2
                    ),
                    "available_gb": round(
                        psutil.virtual_memory().available / (1024**3), 2
                    ),
                },
                "disk": self._get_disk_info(),
                "gpu": self.get_gpu_info(),
            }
        except Exception as e:
            self.logger.error(f"Error getting hardware info: {e}")
            return {}

    def _get_performance_info(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        try:
            vm = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "cpu_percent_total": psutil.cpu_percent(interval=0.1),
                "cpu_percent_per_core": psutil.cpu_percent(interval=0.1, percpu=True),
                "memory_percent": vm.percent,
                "memory_available_gb": round(vm.available / (1024**3), 2),
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "process_count": len(psutil.pids()),
            }
        except Exception as e:
            self.logger.error(f"Error getting performance info: {e}")
            return {}

    def _get_disk_info(self) -> List[Dict[str, Any]]:
        """Get disk information"""
        disks = []
        try:
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append(
                        {
                            "device": partition.device,
                            "mountpoint": partition.mountpoint,
                            "fstype": partition.fstype,
                            "total_gb": round(usage.total / (1024**3), 2),
                            "used_gb": round(usage.used / (1024**3), 2),
                            "free_gb": round(usage.free / (1024**3), 2),
                            "percent": usage.percent,
                        }
                    )
                except PermissionError:
                    continue
        except Exception as e:
            self.logger.error(f"Error getting disk info: {e}")

        return disks

    def get_gpu_info(self) -> List[Dict[str, Any]]:
        """Get GPU information using pynvml (Linux-compatible)"""
        if self._gpu_info_cache is not None:
            return self._gpu_info_cache

        gpus = []

        # Try pynvml first (NVIDIA GPUs)
        try:
            import pynvml

            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()

            for i in range(device_count):
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    name = pynvml.nvmlDeviceGetName(handle)

                    # Handle both bytes and str return types
                    if isinstance(name, bytes):
                        name = name.decode("utf-8")

                    memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)

                    driver_version = pynvml.nvmlSystemGetDriverVersion()
                    if isinstance(driver_version, bytes):
                        driver_version = driver_version.decode("utf-8")

                    gpus.append(
                        {
                            "id": i,
                            "name": name,
                            "vendor": "NVIDIA",
                            "memory_total_bytes": memory_info.total,
                            "memory_total_gb": round(
                                memory_info.total / (1024**3), 2
                            ),
                            "memory_free_gb": round(
                                memory_info.free / (1024**3), 2
                            ),
                            "driver_version": driver_version,
                        }
                    )
                except Exception as e:
                    self.logger.warning(f"Error getting info for GPU {i}: {e}")

            pynvml.nvmlShutdown()

            if gpus:
                self._gpu_info_cache = gpus
                return gpus

        except ImportError:
            self.logger.debug("pynvml not available")
        except Exception as e:
            self.logger.debug(f"pynvml error: {e}")

        # Try lspci for AMD/Intel GPUs on Linux
        if platform.system() == "Linux":
            try:
                gpus = self._get_gpu_info_lspci()
                if gpus:
                    self._gpu_info_cache = gpus
                    return gpus
            except Exception as e:
                self.logger.debug(f"lspci error: {e}")

        # No GPU detected
        self._gpu_info_cache = []
        return []

    def _get_gpu_info_lspci(self) -> List[Dict[str, Any]]:
        """Get GPU info using lspci on Linux"""
        gpus = []

        try:
            result = subprocess.run(
                ["lspci"], capture_output=True, text=True, timeout=5
            )

            if result.returncode != 0:
                return []

            gpu_id = 0
            for line in result.stdout.split("\n"):
                line_lower = line.lower()
                if "vga" in line_lower or "3d" in line_lower:
                    vendor = "Unknown"
                    if "nvidia" in line_lower:
                        vendor = "NVIDIA"
                    elif "amd" in line_lower or "ati" in line_lower:
                        vendor = "AMD"
                    elif "intel" in line_lower:
                        vendor = "Intel"

                    gpus.append(
                        {
                            "id": gpu_id,
                            "name": line.split(": ", 1)[1] if ": " in line else line,
                            "vendor": vendor,
                            "memory_total_gb": 0,  # Not available via lspci
                            "driver_version": "Unknown",
                        }
                    )
                    gpu_id += 1

        except FileNotFoundError:
            self.logger.debug("lspci not found")
        except Exception as e:
            self.logger.error(f"Error running lspci: {e}")

        return gpus

    def _get_vulkan_info(self) -> Dict[str, Any]:
        """Check Vulkan support"""
        try:
            # Try vulkaninfo command
            result = subprocess.run(
                ["vulkaninfo", "--summary"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return {
                    "supported": True,
                    "details": "Vulkan detected",
                }

        except FileNotFoundError:
            pass
        except Exception as e:
            self.logger.debug(f"Vulkan check error: {e}")

        return {"supported": False, "details": "Vulkan not detected"}

    def is_gpu_available(self) -> bool:
        """Check if at least one GPU is available"""
        gpus = self.get_gpu_info()
        return len(gpus) > 0

    def get_gpu_count(self) -> int:
        """Get number of available GPUs"""
        return len(self.get_gpu_info())

    def get_performance_score(self) -> float:
        """
        Calculate a performance score (0-100) based on hardware

        Scoring:
        - CPU cores: 20 points
        - RAM: 30 points
        - GPU: 40 points
        - Disk speed: 10 points
        """
        score = 0.0

        try:
            # CPU score (0-20 points)
            cpu_cores = psutil.cpu_count(logical=True) or 1
            cpu_score = min(20, (cpu_cores / 16) * 20)
            score += cpu_score

            # RAM score (0-30 points)
            ram_gb = psutil.virtual_memory().total / (1024**3)
            ram_score = min(30, (ram_gb / 32) * 30)
            score += ram_score

            # GPU score (0-40 points)
            gpu_count = self.get_gpu_count()
            if gpu_count > 0:
                gpus = self.get_gpu_info()
                # Check if NVIDIA GPU (better for Real-ESRGAN)
                has_nvidia = any(g.get("vendor") == "NVIDIA" for g in gpus)
                gpu_score = 20 if has_nvidia else 10
                gpu_score += min(20, gpu_count * 10)
                score += gpu_score

            # Disk speed score (simplified, 0-10 points)
            # Assume SSD if read speed > 100 MB/s
            score += 10  # Default to 10 for simplicity

        except Exception as e:
            self.logger.error(f"Error calculating performance score: {e}")
            score = 50  # Default score

        return round(score, 1)

    def get_mac_address(self) -> str:
        """Get MAC address for client identification"""
        try:
            mac = uuid.getnode()
            mac_str = ":".join(
                ["{:02x}".format((mac >> elements) & 0xFF) for elements in range(0, 48, 8)][
                    ::-1
                ]
            )
            return mac_str
        except Exception as e:
            self.logger.error(f"Error getting MAC address: {e}")
            return "00:00:00:00:00:00"

    def get_memory_gb(self) -> float:
        """Get total system memory in GB"""
        try:
            return round(psutil.virtual_memory().total / (1024**3), 2)
        except:
            return 0.0

    def get_available_memory_gb(self) -> float:
        """Get available system memory in GB"""
        try:
            return round(psutil.virtual_memory().available / (1024**3), 2)
        except:
            return 0.0

    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        try:
            return psutil.cpu_percent(interval=0.1)
        except:
            return 0.0

    def get_memory_usage(self) -> float:
        """Get current memory usage percentage"""
        try:
            return psutil.virtual_memory().percent
        except:
            return 0.0
