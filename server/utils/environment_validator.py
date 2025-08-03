# server/utils/environment_validator.py
"""
Validateur d'environnement pour le serveur d'upscaling distribué
Vérifie toutes les dépendances et la configuration du système
"""

import datetime
import os
import sys
import shutil
from pathlib import Path
from typing import List, Tuple, Dict, Any
import logging

def setup_logging() -> logging.Logger:
    """Configure le logging pour la validation"""
    logger = logging.getLogger("environment_validator")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

def validate_environment() -> Tuple[bool, List[str]]:
    """
    Valide l'environnement complet du serveur
    Retourne (is_valid, issues_list)
    """
    logger = setup_logging()
    issues = []
    
    # 1. Validation des dépendances Python
    python_issues = _validate_python_dependencies()
    issues.extend(python_issues)
    
    # 2. Validation des exécutables
    executable_issues = _validate_executables()
    issues.extend(executable_issues)
    
    # 3. Validation des dossiers de travail
    directory_issues = _validate_directories()
    issues.extend(directory_issues)
    
    # 4. Validation de la configuration
    config_issues = _validate_configuration()
    issues.extend(config_issues)
    
    # 5. Validation du hardware
    hardware_issues = _validate_hardware()
    issues.extend(hardware_issues)
    
    is_valid = len(issues) == 0
    
    if issues:
        logger.warning("Problèmes détectés dans l'environnement:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    else:
        logger.info("✅ Environnement validé avec succès")
    
    return is_valid, issues

def _validate_python_dependencies() -> List[str]:
    """Valide les dépendances Python requises"""
    issues = []
    
    required_modules = [
        ('psutil', 'Monitoring système'),
        ('PyQt5', 'Interface graphique (optionnel)'),
        ('asyncio', 'Programmation asynchrone'),
        ('pathlib', 'Gestion des chemins'),
        ('json', 'Sérialisation JSON'),
        ('logging', 'Système de logs'),
    ]
    
    optional_modules = [
        ('pynvml', 'Détection GPU NVIDIA'),
    ]
    
    for module_name, description in required_modules:
        try:
            __import__(module_name)
        except ImportError:
            issues.append(f"Module Python requis manquant: {module_name} ({description})")
    
    for module_name, description in optional_modules:
        try:
            __import__(module_name)
        except ImportError:
            # Les modules optionnels ne génèrent que des avertissements
            pass
    
    return issues

def _validate_executables() -> List[str]:
    """Valide la présence des exécutables requis"""
    issues = []
    
    try:
        from utils.executable_detector import executable_detector
        status = executable_detector.get_all_executables_status()
        
        # Vérification des exécutables requis
        for name, info in status.items():
            if name == 'summary':
                continue
            if info['required'] and not info['path']:
                issues.append(f"{name} requis pour l'upscaling - {name} non trouvé dans PATH")
        
    except ImportError:
        issues.append("Détecteur d'exécutables non disponible")
    except Exception as e:
        issues.append(f"Erreur lors de la détection des exécutables: {e}")
    
    return issues

def _validate_directories() -> List[str]:
    """Valide la structure des dossiers"""
    issues = []
    
    try:
        # Dossiers requis
        required_dirs = [
            "temp",
            "work",
            "output",
            "logs"
        ]
        
        project_root = _find_project_root()
        server_root = project_root / "server"
        
        for dir_name in required_dirs:
            dir_path = server_root / dir_name
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    issues.append(f"Impossible de créer le dossier {dir_path}: {e}")
    
    except Exception as e:
        issues.append(f"Erreur lors de la validation des dossiers: {e}")
    
    return issues

def _validate_configuration() -> List[str]:
    """Valide la configuration du système"""
    issues = []
    
    try:
        # Vérification de la configuration de base
        from config.settings import config
        
        # Ports réseau
        port = config.get("server.port", 8765)
        if not isinstance(port, int) or not (1024 <= port <= 65535):
            issues.append(f"Port serveur invalide: {port}")
        
        # Limites de ressources
        gpu_memory = config.get("processing.gpu_memory_limit", 4096)
        if gpu_memory < 512:
            issues.append("Limite mémoire GPU trop faible (< 512MB)")
    
    except ImportError:
        issues.append("Configuration système non disponible")
    except Exception as e:
        issues.append(f"Erreur lors de la validation de la configuration: {e}")
    
    return issues

def _validate_hardware() -> List[str]:
    """Valide la détection du hardware"""
    issues = []
    
    try:
        from utils.hardware_detector import hardware_detector
        
        # Test de détection du système
        system_info = hardware_detector.detect_system_info()
        
        if not system_info:
            issues.append("Impossible de détecter les informations système")
        else:
            # Vérification GPU
            if not system_info.gpus or len(system_info.gpus) == 0:
                issues.append("Aucun GPU détecté - performances limitées")
            
            # Vérification RAM
            if system_info.ram_total_gb < 4:
                issues.append("RAM insuffisante (< 4GB) - performances limitées")
    
    except ImportError:
        issues.append("Détecteur hardware non disponible")
    except Exception as e:
        issues.append(f"Erreur lors de la détection hardware: {e}")
    
    return issues

def _find_project_root() -> Path:
    """Trouve la racine du projet UpscalingByNetwork"""
    current = Path(__file__).resolve()
    
    while current.parent != current:
        if current.name == "UpscalingByNetwork":
            return current
        current = current.parent
    
    # Fallback
    return Path(__file__).resolve().parent.parent

def check_dependency(command: str) -> bool:
    """Vérifie si une commande est disponible dans le PATH"""
    return shutil.which(command) is not None

def generate_environment_report() -> Dict[str, Any]:
    """Génère un rapport complet de l'environnement"""
    logger = setup_logging()
    
    report = {
        'timestamp': str(datetime.now()),
        'system': {
            'platform': sys.platform,
            'python_version': sys.version,
            'working_directory': str(Path.cwd()),
            'project_root': str(_find_project_root())
        },
        'validation': {},
        'executables': {},
        'hardware': {},
        'configuration': {}
    }
    
    # Validation générale
    is_valid, issues = validate_environment()
    report['validation'] = {
        'is_valid': is_valid,
        'issues': issues
    }
    
    # Statut des exécutables
    try:
        from utils.executable_detector import executable_detector
        report['executables'] = executable_detector.get_all_executables_status()
    except Exception as e:
        report['executables'] = {'error': str(e)}
    
    # Informations hardware
    try:
        from utils.hardware_detector import hardware_detector
        system_info = hardware_detector.detect_system_info()
        if system_info:
            report['hardware'] = {
                'gpu_count': len(system_info.gpus),
                'primary_gpu': system_info.gpus[0].name if system_info.gpus else None,
                'cpu_model': system_info.cpu.model,
                'ram_total_gb': system_info.ram_total_gb,
                'is_laptop': system_info.is_laptop
            }
    except Exception as e:
        report['hardware'] = {'error': str(e)}
    
    # Configuration
    try:
        from config.settings import config
        report['configuration'] = {
            'server_port': config.get("server.port"),
            'server_host': config.get("server.host"),
            'gpu_memory_limit': config.get("processing.gpu_memory_limit"),
            'log_level': config.get("monitoring.log_level")
        }
    except Exception as e:
        report['configuration'] = {'error': str(e)}
    
    return report

def print_environment_report():
    """Affiche un rapport complet de l'environnement"""
    from datetime import datetime
    
    report = generate_environment_report()
    
    print("\n" + "="*70)
    print("🔍 RAPPORT D'ENVIRONNEMENT SERVEUR UPSCALING")
    print("="*70)
    print(f"📅 Date: {report['timestamp']}")
    print(f"🖥️  Plateforme: {report['system']['platform']}")
    print(f"🐍 Python: {report['system']['python_version']}")
    print(f"📁 Projet: {report['system']['project_root']}")
    print()
    
    # Validation
    validation = report['validation']
    if validation['is_valid']:
        print("✅ VALIDATION: SUCCÈS")
    else:
        print("❌ VALIDATION: ÉCHEC")
        for issue in validation['issues']:
            print(f"   - {issue}")
    print()
    
    # Exécutables
    print("🔧 EXÉCUTABLES:")
    if 'error' in report['executables']:
        print(f"   ❌ Erreur: {report['executables']['error']}")
    else:
        for name, info in report['executables'].items():
            if name == 'summary':
                continue
            status = "✅" if info['path'] else "❌"
            required = "REQUIS" if info['required'] else "OPTIONNEL"
            print(f"   {status} {name}: {info['path'] or 'NON TROUVÉ'} ({required})")
    print()
    
    # Hardware
    print("🖥️  HARDWARE:")
    if 'error' in report['hardware']:
        print(f"   ❌ Erreur: {report['hardware']['error']}")
    else:
        hw = report['hardware']
        print(f"   GPU: {hw.get('primary_gpu', 'Non détecté')} ({hw.get('gpu_count', 0)} total)")
        print(f"   CPU: {hw.get('cpu_model', 'Non détecté')}")
        print(f"   RAM: {hw.get('ram_total_gb', 0):.1f} GB")
        print(f"   Type: {'Laptop' if hw.get('is_laptop') else 'Desktop'}")
    print()
    
    # Configuration
    print("⚙️  CONFIGURATION:")
    if 'error' in report['configuration']:
        print(f"   ❌ Erreur: {report['configuration']['error']}")
    else:
        cfg = report['configuration']
        print(f"   Serveur: {cfg.get('server_host')}:{cfg.get('server_port')}")
        print(f"   Limite GPU: {cfg.get('gpu_memory_limit')} MB")
        print(f"   Log Level: {cfg.get('log_level')}")
    
    print("="*70)

if __name__ == "__main__":
    print_environment_report()