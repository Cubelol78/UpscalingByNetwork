#!/usr/bin/env python3
"""
Setup script for the Linux client
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file) as f:
        requirements = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]

setup(
    name="upscaling-client-linux",
    version="1.0.0",
    description="Distributed image upscaling client for Linux",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Upscaling Network Team",
    python_requires=">=3.8",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "upscaling-client=cli.commands:cli",
            "upscaling-client-gui=client_gui:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Graphics",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",
    ],
    keywords="upscaling image-processing real-esrgan distributed",
    project_urls={
        "Source": "https://github.com/yourusername/UpscalingByNetwork",
        "Bug Reports": "https://github.com/yourusername/UpscalingByNetwork/issues",
    },
)
