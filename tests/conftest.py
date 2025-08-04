# UpscalingByNetwork/tests/conftest.py

"""
Configuration pour les tests
UpscalingByNetwork/tests/conftest.py
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path

@pytest.fixture(scope="session")
def event_loop():
    """Crée un event loop pour les tests asynchrones"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def temp_work_dir():
    """Crée un dossier de travail temporaire"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)

@pytest.fixture
def mock_video_file(temp_work_dir):
    """Crée un fichier vidéo factice pour les tests"""
    video_file = temp_work_dir / "test_video.mp4"
    
    # Création d'un fichier avec des données factices
    video_file.write_bytes(b"fake video data for testing" * 1000)
    
    yield video_file

@pytest.fixture
def mock_image_files(temp_work_dir):
    """Crée des fichiers images factices"""
    images_dir = temp_work_dir / "images"
    images_dir.mkdir()
    
    image_files = []
    for i in range(10):
        img_file = images_dir / f"frame_{i:06d}.png"
        img_file.write_bytes(b"fake png data" * 100)
        image_files.append(img_file)
    
    yield image_files