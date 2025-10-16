"""
Asset Path Resolver for UpscalingByNetwork Client

This module provides centralized path resolution for all external assets including
FFmpeg, Real-ESRGAN executables, and model files. It handles multiple deployment
scenarios including PyInstaller bundles, development environments, and system
installations.

Features:
- Automatic platform detection (Windows, Linux, macOS)
- PyInstaller bundle detection
- Environment variable support
- Intelligent search across multiple locations
- Path caching for performance
- Comprehensive logging

Usage:
    from utils.asset_paths import get_ffmpeg_path, get_realesrgan_path

    ffmpeg = get_ffmpeg_path()
    realesrgan = get_realesrgan_path()
"""

import os
import sys
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from functools import lru_cache


class AssetPathResolver:
    """
    Centralized resolver for all external asset paths.

    This class manages the detection and resolution of paths to external
    executables and resources required by the UpscalingByNetwork client.
    It supports multiple deployment scenarios and platforms.

    Attributes:
        platform (str): Current platform ('windows', 'linux', 'darwin')
        is_frozen (bool): True if running in PyInstaller bundle
        project_root (Path): Root directory of the project
        client_root (Path): Root directory of the client
        _path_cache (Dict): Cache for resolved paths
    """

    def __init__(self):
        """Initialize the asset path resolver."""
        self.logger = logging.getLogger(__name__)

        # Platform detection
        self.platform = sys.platform.lower()
        if self.platform.startswith('win'):
            self.platform = 'windows'
        elif self.platform.startswith('darwin'):
            self.platform = 'darwin'
        elif self.platform.startswith('linux'):
            self.platform = 'linux'

        # PyInstaller detection
        self.is_frozen = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

        # Determine project root
        self.project_root = self._find_project_root()
        self.client_root = self._find_client_root()

        # Cache for resolved paths
        self._path_cache: Dict[str, Optional[Path]] = {}

        self.logger.info(f"AssetPathResolver initialized")
        self.logger.info(f"  Platform: {self.platform}")
        self.logger.info(f"  Frozen: {self.is_frozen}")
        self.logger.info(f"  Project root: {self.project_root}")
        self.logger.info(f"  Client root: {self.client_root}")

    def _find_project_root(self) -> Path:
        """
        Find the root directory of the UpscalingByNetwork project.

        Searches upward from the current file location until finding
        the UpscalingByNetwork directory or uses fallback strategies
        for different deployment scenarios.

        Returns:
            Path: The project root directory
        """
        if self.is_frozen:
            # PyInstaller bundle - use _MEIPASS or executable directory
            if hasattr(sys, '_MEIPASS'):
                return Path(sys._MEIPASS)
            else:
                return Path(sys.executable).parent

        # Development environment - find by directory name
        current = Path(__file__).resolve()

        # Traverse upward to find UpscalingByNetwork
        while current.parent != current:
            if current.name == "UpscalingByNetwork":
                return current
            if (current / "UpscalingByNetwork").exists():
                return current / "UpscalingByNetwork"
            current = current.parent

        # Fallback: this file is in client/linux/utils/
        # So project root is 3 levels up
        current_file = Path(__file__).resolve()
        if "client" in current_file.parts and "utils" in current_file.parts:
            # Go up: utils -> linux -> client -> UpscalingByNetwork
            return current_file.parent.parent.parent

        # Last resort: use current working directory
        return Path.cwd()

    def _find_client_root(self) -> Path:
        """
        Find the root directory of the client.

        Returns:
            Path: The client root directory
        """
        if self.is_frozen:
            # In frozen app, client root is same as bundle root
            return self.project_root

        # Look for client directory under project root
        client_path = self.project_root / "client"
        if client_path.exists():
            # Check for platform-specific subdirectory
            platform_dir = client_path / self.platform
            if platform_dir.exists():
                return platform_dir
            # Check for 'linux' as fallback (common structure)
            linux_dir = client_path / "linux"
            if linux_dir.exists():
                return linux_dir
            return client_path

        # Fallback: this file is in client/linux/utils/
        current_file = Path(__file__).resolve()
        if "client" in current_file.parts:
            # Go up: utils -> linux (or platform) -> client
            return current_file.parent.parent

        return self.project_root

    def _get_executable_name(self, base_name: str) -> str:
        """
        Get platform-specific executable name.

        Args:
            base_name: Base name of the executable (without extension)

        Returns:
            str: Executable name with platform-specific extension
        """
        if self.platform == 'windows':
            return f"{base_name}.exe"
        return base_name

    def _search_paths(self, executable_name: str, search_dirs: List[Path]) -> Optional[Path]:
        """
        Search for an executable in multiple directories.

        Args:
            executable_name: Name of the executable to find
            search_dirs: List of directories to search

        Returns:
            Optional[Path]: Path to executable if found, None otherwise
        """
        for search_dir in search_dirs:
            if not search_dir:
                continue

            candidate = search_dir / executable_name
            self.logger.debug(f"  Checking: {candidate}")

            if candidate.exists() and candidate.is_file():
                # Verify it's executable on Unix-like systems
                if self.platform != 'windows':
                    if not os.access(candidate, os.X_OK):
                        self.logger.debug(f"  File exists but not executable: {candidate}")
                        continue

                self.logger.info(f"  Found: {candidate}")
                return candidate.resolve()

        return None

    def _check_system_path(self, executable_name: str) -> Optional[Path]:
        """
        Check if executable exists in system PATH.

        Args:
            executable_name: Name of the executable to find

        Returns:
            Optional[Path]: Path to executable if found in PATH, None otherwise
        """
        system_path = shutil.which(executable_name)
        if system_path:
            path = Path(system_path)
            self.logger.info(f"  Found in system PATH: {path}")
            return path
        return None

    def _check_environment_variable(self, var_name: str) -> Optional[Path]:
        """
        Check if path is specified in environment variable.

        Args:
            var_name: Name of the environment variable

        Returns:
            Optional[Path]: Path from environment variable if valid, None otherwise
        """
        env_path = os.environ.get(var_name)
        if env_path:
            path = Path(env_path)
            if path.exists():
                self.logger.info(f"  Found via {var_name}: {path}")
                return path.resolve()
            else:
                self.logger.warning(f"  {var_name} set but path doesn't exist: {env_path}")
        return None

    def get_ffmpeg_path(self) -> Optional[Path]:
        """
        Resolve the path to the FFmpeg executable.

        Search order:
        1. FFMPEG_PATH environment variable
        2. Cached path
        3. PyInstaller bundle
        4. Client dependencies directory
        5. Project-level dependencies
        6. System PATH

        Returns:
            Optional[Path]: Path to FFmpeg executable, or None if not found
        """
        cache_key = 'ffmpeg'
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        self.logger.info("Searching for FFmpeg...")

        # Check environment variable first
        env_path = self._check_environment_variable('FFMPEG_PATH')
        if env_path:
            self._path_cache[cache_key] = env_path
            return env_path

        executable_name = self._get_executable_name('ffmpeg')

        # Build search paths
        search_dirs = [
            # PyInstaller bundle
            self.project_root if self.is_frozen else None,
            self.project_root / 'bin' if self.is_frozen else None,

            # NEW: Assets directory (centralized binaries)
            self.project_root / 'assets' / 'ffmpeg' / self.platform / 'x64',
            self.project_root / 'assets' / 'ffmpeg' / self.platform.lower() / 'x64',
            self.project_root / 'assets' / 'ffmpeg' / self.platform,
            self.project_root / 'assets' / 'ffmpeg',

            # Client dependencies
            self.client_root / 'ffmpeg',
            self.client_root / 'ffmpeg' / 'bin',
            self.client_root / 'dependencies' / 'ffmpeg',
            self.client_root / 'dependencies' / 'ffmpeg' / 'bin',

            # Project-level dependencies
            self.project_root / 'ffmpeg',
            self.project_root / 'ffmpeg' / 'bin',
            self.project_root / 'dependencies' / 'ffmpeg',
            self.project_root / 'dependencies' / 'ffmpeg' / 'bin',

            # Platform-specific subdirectories
            self.client_root / 'ffmpeg' / self.platform.capitalize(),
            self.project_root / 'ffmpeg' / self.platform.capitalize(),
        ]

        # Search in directories
        result = self._search_paths(executable_name, search_dirs)
        if result:
            self._path_cache[cache_key] = result
            return result

        # Check system PATH
        result = self._check_system_path(executable_name)
        if result:
            self._path_cache[cache_key] = result
            return result

        self.logger.warning("FFmpeg not found")
        self._path_cache[cache_key] = None
        return None

    def get_ffprobe_path(self) -> Optional[Path]:
        """
        Resolve the path to the FFprobe executable.

        FFprobe is typically in the same directory as FFmpeg.

        Search order:
        1. FFPROBE_PATH environment variable
        2. Cached path
        3. Same directory as FFmpeg
        4. Same search paths as FFmpeg
        5. System PATH

        Returns:
            Optional[Path]: Path to FFprobe executable, or None if not found
        """
        cache_key = 'ffprobe'
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        self.logger.info("Searching for FFprobe...")

        # Check environment variable first
        env_path = self._check_environment_variable('FFPROBE_PATH')
        if env_path:
            self._path_cache[cache_key] = env_path
            return env_path

        executable_name = self._get_executable_name('ffprobe')

        # Try to derive from FFmpeg path
        ffmpeg_path = self.get_ffmpeg_path()
        if ffmpeg_path:
            ffprobe_in_ffmpeg_dir = ffmpeg_path.parent / executable_name
            if ffprobe_in_ffmpeg_dir.exists():
                self.logger.info(f"  Found alongside FFmpeg: {ffprobe_in_ffmpeg_dir}")
                self._path_cache[cache_key] = ffprobe_in_ffmpeg_dir
                return ffprobe_in_ffmpeg_dir

        # Use same search paths as FFmpeg
        search_dirs = [
            self.project_root if self.is_frozen else None,
            self.project_root / 'bin' if self.is_frozen else None,
            self.client_root / 'ffmpeg',
            self.client_root / 'ffmpeg' / 'bin',
            self.client_root / 'dependencies' / 'ffmpeg',
            self.client_root / 'dependencies' / 'ffmpeg' / 'bin',
            self.project_root / 'ffmpeg',
            self.project_root / 'ffmpeg' / 'bin',
            self.project_root / 'dependencies' / 'ffmpeg',
            self.project_root / 'dependencies' / 'ffmpeg' / 'bin',
            self.client_root / 'ffmpeg' / self.platform.capitalize(),
            self.project_root / 'ffmpeg' / self.platform.capitalize(),
        ]

        result = self._search_paths(executable_name, search_dirs)
        if result:
            self._path_cache[cache_key] = result
            return result

        result = self._check_system_path(executable_name)
        if result:
            self._path_cache[cache_key] = result
            return result

        self.logger.warning("FFprobe not found")
        self._path_cache[cache_key] = None
        return None

    def get_realesrgan_path(self) -> Optional[Path]:
        """
        Resolve the path to the Real-ESRGAN executable.

        Search order:
        1. REALESRGAN_PATH environment variable
        2. Cached path
        3. PyInstaller bundle
        4. Client dependencies directory
        5. Project-level dependencies
        6. System PATH

        Returns:
            Optional[Path]: Path to Real-ESRGAN executable, or None if not found
        """
        cache_key = 'realesrgan'
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        self.logger.info("Searching for Real-ESRGAN...")

        # Check environment variable first
        env_path = self._check_environment_variable('REALESRGAN_PATH')
        if env_path:
            self._path_cache[cache_key] = env_path
            return env_path

        executable_name = self._get_executable_name('realesrgan-ncnn-vulkan')

        # Build search paths
        search_dirs = [
            # PyInstaller bundle
            self.project_root if self.is_frozen else None,
            self.project_root / 'bin' if self.is_frozen else None,

            # NEW: Assets directory (centralized binaries)
            self.project_root / 'assets' / 'realesrgan' / self.platform / 'x64',
            self.project_root / 'assets' / 'realesrgan' / self.platform.lower() / 'x64',
            self.project_root / 'assets' / 'realesrgan' / self.platform,
            self.project_root / 'assets' / 'realesrgan',

            # Client dependencies
            self.client_root / 'realesrgan-ncnn-vulkan',
            self.client_root / 'realesrgan-ncnn-vulkan' / 'bin',
            self.client_root / 'dependencies' / 'realesrgan-ncnn-vulkan',
            self.client_root / 'dependencies' / 'realesrgan-ncnn-vulkan' / 'bin',

            # Project-level dependencies
            self.project_root / 'realesrgan-ncnn-vulkan',
            self.project_root / 'realesrgan-ncnn-vulkan' / 'bin',
            self.project_root / 'dependencies' / 'realesrgan-ncnn-vulkan',
            self.project_root / 'dependencies' / 'realesrgan-ncnn-vulkan' / 'bin',

            # Platform-specific subdirectories
            self.client_root / 'realesrgan-ncnn-vulkan' / self.platform.capitalize(),
            self.project_root / 'realesrgan-ncnn-vulkan' / self.platform.capitalize(),
        ]

        result = self._search_paths(executable_name, search_dirs)
        if result:
            self._path_cache[cache_key] = result
            return result

        result = self._check_system_path(executable_name)
        if result:
            self._path_cache[cache_key] = result
            return result

        self.logger.warning("Real-ESRGAN not found")
        self._path_cache[cache_key] = None
        return None

    def get_realesrgan_models_path(self) -> Optional[Path]:
        """
        Resolve the path to the Real-ESRGAN models directory.

        Search order:
        1. REALESRGAN_MODELS_PATH environment variable
        2. Cached path
        3. Same directory as Real-ESRGAN executable
        4. Models subdirectory of Real-ESRGAN directory

        Returns:
            Optional[Path]: Path to models directory, or None if not found
        """
        cache_key = 'realesrgan_models'
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        self.logger.info("Searching for Real-ESRGAN models...")

        # Check environment variable first
        env_path = self._check_environment_variable('REALESRGAN_MODELS_PATH')
        if env_path and env_path.is_dir():
            self._path_cache[cache_key] = env_path
            return env_path

        # Try to derive from Real-ESRGAN executable path
        realesrgan_path = self.get_realesrgan_path()
        if realesrgan_path:
            # Check same directory
            models_in_same_dir = realesrgan_path.parent / 'models'
            if models_in_same_dir.exists() and models_in_same_dir.is_dir():
                self.logger.info(f"  Found models alongside executable: {models_in_same_dir}")
                self._path_cache[cache_key] = models_in_same_dir
                return models_in_same_dir

            # Check parent directory
            parent_models = realesrgan_path.parent.parent / 'models'
            if parent_models.exists() and parent_models.is_dir():
                self.logger.info(f"  Found models in parent directory: {parent_models}")
                self._path_cache[cache_key] = parent_models
                return parent_models

        # Search in known locations
        search_dirs = [
            # NEW: Assets directory (centralized models)
            self.project_root / 'assets' / 'models',

            self.client_root / 'realesrgan-ncnn-vulkan' / 'models',
            self.client_root / 'models',
            self.project_root / 'realesrgan-ncnn-vulkan' / 'models',
            self.project_root / 'models',
            self.client_root / 'dependencies' / 'realesrgan-ncnn-vulkan' / 'models',
            self.project_root / 'dependencies' / 'realesrgan-ncnn-vulkan' / 'models',
        ]

        for models_dir in search_dirs:
            if models_dir and models_dir.exists() and models_dir.is_dir():
                # Verify it contains model files
                model_files = list(models_dir.glob('*.bin')) + list(models_dir.glob('*.param'))
                if model_files:
                    self.logger.info(f"  Found models directory: {models_dir}")
                    self._path_cache[cache_key] = models_dir
                    return models_dir

        self.logger.warning("Real-ESRGAN models directory not found")
        self._path_cache[cache_key] = None
        return None

    def verify_all_assets(self) -> Dict[str, Tuple[bool, Optional[Path]]]:
        """
        Verify the availability of all required assets.

        Returns:
            Dict[str, Tuple[bool, Optional[Path]]]: Dictionary mapping asset names
                to tuples of (found: bool, path: Optional[Path])
        """
        results = {
            'ffmpeg': (False, None),
            'ffprobe': (False, None),
            'realesrgan': (False, None),
            'realesrgan_models': (False, None),
        }

        ffmpeg_path = self.get_ffmpeg_path()
        results['ffmpeg'] = (ffmpeg_path is not None, ffmpeg_path)

        ffprobe_path = self.get_ffprobe_path()
        results['ffprobe'] = (ffprobe_path is not None, ffprobe_path)

        realesrgan_path = self.get_realesrgan_path()
        results['realesrgan'] = (realesrgan_path is not None, realesrgan_path)

        models_path = self.get_realesrgan_models_path()
        results['realesrgan_models'] = (models_path is not None, models_path)

        return results

    def clear_cache(self):
        """Clear the internal path cache."""
        self._path_cache.clear()
        self.logger.info("Path cache cleared")

    def get_asset_info(self) -> Dict[str, any]:
        """
        Get comprehensive information about all assets.

        Returns:
            Dict: Detailed information about asset paths and environment
        """
        verification = self.verify_all_assets()

        return {
            'platform': self.platform,
            'is_frozen': self.is_frozen,
            'project_root': str(self.project_root),
            'client_root': str(self.client_root),
            'assets': {
                name: {
                    'found': found,
                    'path': str(path) if path else None,
                }
                for name, (found, path) in verification.items()
            },
            'environment_variables': {
                'FFMPEG_PATH': os.environ.get('FFMPEG_PATH'),
                'FFPROBE_PATH': os.environ.get('FFPROBE_PATH'),
                'REALESRGAN_PATH': os.environ.get('REALESRGAN_PATH'),
                'REALESRGAN_MODELS_PATH': os.environ.get('REALESRGAN_MODELS_PATH'),
            }
        }


# Global singleton instance
_resolver_instance: Optional[AssetPathResolver] = None


def get_resolver() -> AssetPathResolver:
    """
    Get the global AssetPathResolver instance.

    Returns:
        AssetPathResolver: The global resolver instance
    """
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = AssetPathResolver()
    return _resolver_instance


# Convenience functions for direct access
def get_ffmpeg_path() -> Optional[Path]:
    """
    Get the path to the FFmpeg executable.

    Returns:
        Optional[Path]: Path to FFmpeg, or None if not found
    """
    return get_resolver().get_ffmpeg_path()


def get_ffprobe_path() -> Optional[Path]:
    """
    Get the path to the FFprobe executable.

    Returns:
        Optional[Path]: Path to FFprobe, or None if not found
    """
    return get_resolver().get_ffprobe_path()


def get_realesrgan_path() -> Optional[Path]:
    """
    Get the path to the Real-ESRGAN executable.

    Returns:
        Optional[Path]: Path to Real-ESRGAN, or None if not found
    """
    return get_resolver().get_realesrgan_path()


def get_realesrgan_models_path() -> Optional[Path]:
    """
    Get the path to the Real-ESRGAN models directory.

    Returns:
        Optional[Path]: Path to models directory, or None if not found
    """
    return get_resolver().get_realesrgan_models_path()


def verify_all_assets() -> Dict[str, Tuple[bool, Optional[Path]]]:
    """
    Verify the availability of all required assets.

    Returns:
        Dict[str, Tuple[bool, Optional[Path]]]: Asset verification results
    """
    return get_resolver().verify_all_assets()


def clear_cache():
    """Clear the path resolution cache."""
    get_resolver().clear_cache()


if __name__ == "__main__":
    """
    CLI interface for testing asset path resolution.

    Run this module directly to check asset availability:
        python -m utils.asset_paths
    """
    import json

    # Configure logging for CLI
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(name)s - %(message)s'
    )

    print("=" * 70)
    print("UpscalingByNetwork Client - Asset Path Resolver")
    print("=" * 70)
    print()

    resolver = get_resolver()
    info = resolver.get_asset_info()

    print(f"Platform: {info['platform']}")
    print(f"Frozen (PyInstaller): {info['is_frozen']}")
    print(f"Project Root: {info['project_root']}")
    print(f"Client Root: {info['client_root']}")
    print()

    print("-" * 70)
    print("Asset Status:")
    print("-" * 70)

    all_found = True
    for name, asset_info in info['assets'].items():
        status = "✓ FOUND" if asset_info['found'] else "✗ NOT FOUND"
        path_str = asset_info['path'] if asset_info['path'] else "N/A"
        print(f"{name:20s} {status:15s} {path_str}")
        if not asset_info['found']:
            all_found = False

    print()
    print("-" * 70)
    print("Environment Variables:")
    print("-" * 70)

    for var_name, var_value in info['environment_variables'].items():
        value_str = var_value if var_value else "(not set)"
        print(f"{var_name:25s} {value_str}")

    print()
    print("=" * 70)

    if all_found:
        print("SUCCESS: All required assets found!")
        sys.exit(0)
    else:
        print("WARNING: Some assets are missing. Please install them.")
        print()
        print("Installation hints:")
        print("  FFmpeg: https://ffmpeg.org/download.html")
        print("  Real-ESRGAN: https://github.com/xinntao/Real-ESRGAN/releases")
        sys.exit(1)
