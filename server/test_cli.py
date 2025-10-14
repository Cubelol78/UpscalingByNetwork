#!/usr/bin/env python3
"""
Test script for CLI/headless mode functionality
"""

import sys
import os
from pathlib import Path

# Add paths
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(current_dir))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")

    try:
        import main
        print("  ✓ main.py imported successfully")
    except Exception as e:
        print(f"  ✗ Failed to import main.py: {e}")
        return False

    try:
        import cli
        print("  ✓ cli.py imported successfully")
    except Exception as e:
        print(f"  ✗ Failed to import cli.py: {e}")
        return False

    try:
        import daemon
        print("  ✓ daemon.py imported successfully")
    except Exception as e:
        print(f"  ✗ Failed to import daemon.py: {e}")
        return False

    return True


def test_display_detection():
    """Test display detection"""
    print("\nTesting display detection...")

    try:
        from main import detect_display_available

        has_display = detect_display_available()
        print(f"  Display available: {has_display}")
        print("  ✓ Display detection working")
        return True
    except Exception as e:
        print(f"  ✗ Display detection failed: {e}")
        return False


def test_cli_interface():
    """Test CLI interface creation"""
    print("\nTesting CLI interface...")

    try:
        from cli import ServerCLI, detect_display_available

        # Mock server object
        class MockServer:
            def __init__(self):
                self.host = "0.0.0.0"
                self.port = 8888
                self.running = True
                self.start_time = None

            def get_server_stats(self):
                return {
                    'running': True,
                    'uptime': 0,
                    'clients_connected': 0,
                    'active_jobs': 0,
                    'active_batches': 0,
                    'pending_batches': 0,
                    'total_images_processed': 0
                }

            def get_client_stats(self):
                return []

            def get_job_stats(self):
                return []

        server = MockServer()
        cli = ServerCLI(server, interactive=False, use_rich=False)

        print("  ✓ CLI interface created successfully")
        return True
    except Exception as e:
        print(f"  ✗ CLI interface creation failed: {e}")
        return False


def test_dependency_check():
    """Test dependency checking"""
    print("\nTesting dependency check...")

    try:
        from main import check_dependencies

        deps_ok, missing = check_dependencies(gui_required=False)

        if deps_ok:
            print("  ✓ All required dependencies available")
        else:
            print(f"  ⚠ Missing dependencies: {missing}")

        return True
    except Exception as e:
        print(f"  ✗ Dependency check failed: {e}")
        return False


def test_logging_setup():
    """Test logging configuration"""
    print("\nTesting logging setup...")

    try:
        from main import setup_logging
        import logging

        setup_logging("INFO", Path("logs/test.log"))
        logger = logging.getLogger(__name__)
        logger.info("Test log message")

        print("  ✓ Logging setup successful")
        return True
    except Exception as e:
        print(f"  ✗ Logging setup failed: {e}")
        return False


def test_directory_creation():
    """Test directory creation"""
    print("\nTesting directory creation...")

    try:
        from main import create_directories

        create_directories()

        # Check if directories exist
        required_dirs = [
            "logs",
            "output",
            "server_work",
            "config"
        ]

        all_exist = True
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            if dir_path.exists():
                print(f"  ✓ {dir_name}/ exists")
            else:
                print(f"  ✗ {dir_name}/ missing")
                all_exist = False

        return all_exist
    except Exception as e:
        print(f"  ✗ Directory creation failed: {e}")
        return False


def check_optional_dependencies():
    """Check optional dependencies"""
    print("\nChecking optional dependencies...")

    optional_deps = {
        'rich': 'Rich library (for enhanced CLI)',
        'PyQt5': 'PyQt5 (for GUI mode)',
        'qasync': 'qasync (for GUI mode)',
    }

    for module, description in optional_deps.items():
        try:
            __import__(module)
            print(f"  ✓ {description}")
        except ImportError:
            print(f"  ⚠ {description} not installed (optional)")


def main():
    """Run all tests"""
    print("=" * 70)
    print("UpscalingByNetwork Server - CLI/Headless Mode Tests")
    print("=" * 70)

    tests = [
        test_imports,
        test_dependency_check,
        test_logging_setup,
        test_directory_creation,
        test_display_detection,
        test_cli_interface,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ✗ Test crashed: {e}")
            results.append(False)

    # Optional dependencies check
    check_optional_dependencies()

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
