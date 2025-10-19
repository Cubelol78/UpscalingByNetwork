#!/usr/bin/env python3
"""
System utility functions for UpscalingByNetwork
Provides cross-platform system detection and configuration utilities
"""

import sys
import os


def detect_display_available() -> bool:
    """
    Detect if a display is available for GUI
    Works on Linux, Windows, and macOS
    """
    # Linux/Unix - check DISPLAY or WAYLAND_DISPLAY
    if sys.platform.startswith('linux') or sys.platform == 'darwin':
        if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
            return True
        return False

    # Windows - usually has display unless running as service
    elif sys.platform == 'win32':
        # Check if running as Windows service
        try:
            import win32api
            import win32con
            try:
                # This will fail if running as a service
                win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                return True
            except (OSError, AttributeError, Exception):
                # Service mode or API call failed
                return False
        except ImportError:
            # Assume display available if we can't check
            return True

    return False
