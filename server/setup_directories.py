# server/setup_directories.py
"""
Script de configuration pour créer la structure de dossiers nécessaire
"""

import os
import json
from pathlib import Path

def create_directory_structure():
    """Crée la structure de dossiers nécessaire pour le serveur"""
    
    # Dossier racine du serveur
    server_root = Path(__file__).parent
    
    # Dossiers à créer
    directories = [
        "config",
        "work",
        "input", 
        "output",
        "temp",
        "batches",
        "logs",
        "dependencies",
        "models",
        "realesrgan-ncnn-vulkan/Windows"
    ]
    
    print("🔧 Configuration de la structure de dossiers...")
    
    created_dirs = []
    for directory in directories:
        dir_path = server_root / directory
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(dir_path))
            print(f"✅ Créé: {dir_path}")
        else:
            print(f"📁 Existe déjà: {dir_path}")
    
    # Création du fichier de configuration par défaut
    config_file = server_root / "config" / "server_config.json"
    if not config_file.exists():
        default_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 8765,
                "max_clients": 10,
                "heartbeat_interval": 30,
                "client_timeout": 120,
                "enable_ssl": False,
                "ssl_cert_path": "",
                "ssl_key_path": ""
            },
            "processing": {
                "batch_size": 50,
                "max_concurrent_batches": 5,
                "upscale_factor": 4,
                "realesrgan_model": "RealESRGAN_x4plus",
                "output_format": "png",
                "compression_level": 0,
                "enable_gpu": True,
                "gpu_memory_limit": 8192,
                "tile_size": 256,
                "max_retries": 3,
                "duplicate_threshold": 5
            },
            "storage": {
                "work_directory": "./work",
                "input_directory": "./input",
                "output_directory": "./output",
                "temp_directory": "./temp",
                "batches_directory": "./batches",
                "logs_directory": "./logs",
                "auto_cleanup": True,
                "min_free_space_gb": 5
            },
            "security": {
                "enable_encryption": True,
                "key_exchange_timeout": 30,
                "session_key_size": 256,
                "allowed_clients": []
            },
            "realesrgan": {
                "executable_path": "./realesrgan-ncnn-vulkan/Windows/realesrgan-ncnn-vulkan.exe",
                "models_directory": "./models",
                "default_model": "RealESRGAN_x4plus",
                "default_scale": 4,
                "tile_size": 256,
                "gpu_id": 0,
                "thread_load": "1:2:2",
                "tta_mode": False
            },
            "monitoring": {
                "enable_performance_monitoring": True,
                "log_level": "INFO",
                "max_log_files": 10,
                "metrics_retention_days": 30,
                "enable_gpu_monitoring": True
            },
            "gui": {
                "theme": "dark",
                "auto_refresh_interval": 2000,
                "show_detailed_logs": True,
                "enable_notifications": True,
                "charts_history_points": 100
            }
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        
        print(f"✅ Configuration créée: {config_file}")
    else:
        print(f"📄 Configuration existe: {config_file}")
    
    # Instructions pour Real-ESRGAN
    realesrgan_dir = server_root / "realesrgan-ncnn-vulkan" / "Windows"
    realesrgan_exe = realesrgan_dir / "realesrgan-ncnn-vulkan.exe"
    
    if not realesrgan_exe.exists():
        print("\n⚠️  ATTENTION: Real-ESRGAN non trouvé!")
        print(f"📥 Veuillez télécharger Real-ESRGAN et placer l'exécutable dans:")
        print(f"   {realesrgan_exe}")
        print("🔗 Téléchargement: https://github.com/xinntao/Real-ESRGAN/releases")
        print("📦 Fichier requis: realesrgan-ncnn-vulkan-20220424-windows.zip")
    else:
        print(f"✅ Real-ESRGAN trouvé: {realesrgan_exe}")
    
    print(f"\n🎯 Structure de dossiers configurée!")
    print(f"📁 Dossiers créés: {len(created_dirs)}")
    print(f"📍 Racine serveur: {server_root}")
    
    return True

def check_dependencies():
    """Vérifie les dépendances Python nécessaires"""
    required_packages = [
        'asyncio',
        'websockets', 
        'cryptography',
        'PyQt5',
        'psutil',
        'Pillow'
    ]
    
    missing_packages = []
    
    print("\n🔍 Vérification des dépendances Python...")
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} - MANQUANT")
    
    if missing_packages:
        print(f"\n⚠️  Packages manquants: {', '.join(missing_packages)}")
        print("📦 Installez avec: pip install " + " ".join(missing_packages))
        return False
    else:
        print("✅ Toutes les dépendances sont installées!")
        return True

def main():
    """Fonction principale de configuration"""
    print("🚀 Configuration du serveur d'upscaling distribué")
    print("=" * 50)
    
    # Création de la structure de dossiers
    create_directory_structure()
    
    # Vérification des dépendances
    check_dependencies()
    
    print("\n" + "=" * 50)
    print("✅ Configuration terminée!")
    print("\n📋 Prochaines étapes:")
    print("1. Télécharger Real-ESRGAN si nécessaire")
    print("2. Installer les packages Python manquants")
    print("3. Lancer le serveur avec: python main.py")

if __name__ == "__main__":
    main()