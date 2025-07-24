# check_executables.py
"""
Script de vérification des exécutables pour le projet d'upscaling distribué
Utilise ce script depuis la racine du projet pour vérifier la disponibilité des outils
"""

import sys
import os
from pathlib import Path
import subprocess
import json

def print_banner():
    """Affiche la bannière du script"""
    print("=" * 70)
    print("🔍 VÉRIFICATION DES EXÉCUTABLES - UPSCALING DISTRIBUÉ")
    print("=" * 70)
    print()

def find_project_structure():
    """Détecte la structure du projet"""
    current = Path.cwd()
    
    # Vérification si on est à la racine du projet
    if (current / "server").exists() and (current / "client").exists():
        return {
            'project_root': current,
            'server_root': current / "server",
            'client_root': current / "client" / "windows"
        }
    
    # Vérification si on est dans le dossier serveur
    if current.name == "server" and (current.parent / "client").exists():
        return {
            'project_root': current.parent,
            'server_root': current,
            'client_root': current.parent / "client" / "windows"
        }
    
    # Vérification si on est dans le dossier client
    if current.name == "windows" and (current.parent.parent / "server").exists():
        return {
            'project_root': current.parent.parent,
            'server_root': current.parent.parent / "server",
            'client_root': current
        }
    
    return None

def check_executable(exe_path, name):
    """Vérifie si un exécutable fonctionne"""
    if not exe_path or not Path(exe_path).exists():
        return {
            'name': name,
            'path': exe_path,
            'exists': False,
            'working': False,
            'version': None,
            'error': 'Fichier non trouvé'
        }
    
    try:
        result = subprocess.run(
            [str(exe_path), "-version"],
            capture_output=True,
            timeout=10,
            text=True
        )
        
        if result.returncode == 0:
            # Extraction de la première ligne pour la version
            version_line = (result.stdout + result.stderr).split('\n')[0].strip()
            return {
                'name': name,
                'path': exe_path,
                'exists': True,
                'working': True,
                'version': version_line,
                'error': None
            }
        else:
            return {
                'name': name,
                'path': exe_path,
                'exists': True,
                'working': False,
                'version': None,
                'error': f'Erreur code {result.returncode}'
            }
            
    except subprocess.TimeoutExpired:
        return {
            'name': name,
            'path': exe_path,
            'exists': True,
            'working': False,
            'version': None,
            'error': 'Timeout'
        }
    except Exception as e:
        return {
            'name': name,
            'path': exe_path,
            'exists': True,
            'working': False,
            'version': None,
            'error': str(e)
        }

def find_executables(base_path, component_name):
    """Trouve les exécutables dans un dossier de composant"""
    results = {}
    
    # Real-ESRGAN
    realesrgan_paths = [
        base_path / "realesrgan-ncnn-vulkan" / "realesrgan-ncnn-vulkan.exe",
        base_path / "realesrgan-ncnn-vulkan" / "Windows" / "realesrgan-ncnn-vulkan.exe",
        base_path / "dependencies" / "realesrgan-ncnn-vulkan.exe",
    ]
    
    realesrgan_found = None
    for path in realesrgan_paths:
        if path.exists():
            realesrgan_found = path
            break
    
    results['realesrgan'] = check_executable(realesrgan_found, "Real-ESRGAN")
    
    # FFmpeg
    ffmpeg_paths = [
        base_path / "ffmpeg" / "ffmpeg.exe",
        base_path / "ffmpeg" / "bin" / "ffmpeg.exe",
        base_path / "dependencies" / "ffmpeg.exe",
    ]
    
    ffmpeg_found = None
    for path in ffmpeg_paths:
        if path.exists():
            ffmpeg_found = path
            break
    
    results['ffmpeg'] = check_executable(ffmpeg_found, "FFmpeg")
    
    # FFprobe (même dossier que FFmpeg)
    ffprobe_found = None
    if ffmpeg_found:
        ffprobe_path = ffmpeg_found.parent / "ffprobe.exe"
        if ffprobe_path.exists():
            ffprobe_found = ffprobe_path
    
    results['ffprobe'] = check_executable(ffprobe_found, "FFprobe")
    
    return results

def print_component_status(component_name, results):
    """Affiche le statut d'un composant"""
    print(f"📦 {component_name.upper()}")
    print("-" * 50)
    
    for exe_name, result in results.items():
        status_icon = "✅" if result['working'] else ("📁" if result['exists'] else "❌")
        print(f"{status_icon} {result['name']}")
        
        if result['path']:
            print(f"   📍 Chemin: {result['path']}")
        else:
            print(f"   📍 Chemin: Non trouvé")
        
        if result['working']:
            print(f"   ℹ️  Version: {result['version']}")
        elif result['error']:
            print(f"   ⚠️  Erreur: {result['error']}")
        
        print()

def print_summary(server_results, client_results):
    """Affiche le résumé global"""
    print("=" * 70)
    print("📊 RÉSUMÉ")
    print("=" * 70)
    
    # Comptage serveur
    server_working = sum(1 for r in server_results.values() if r['working'])
    server_total = len(server_results)
    
    # Comptage client
    client_working = sum(1 for r in client_results.values() if r['working'])
    client_total = len(client_results)
    
    print(f"🖥️  Serveur: {server_working}/{server_total} exécutables fonctionnels")
    print(f"💻 Client:  {client_working}/{client_total} exécutables fonctionnels")
    print()
    
    # Statut global
    server_ready = server_results['realesrgan']['working'] and server_results['ffmpeg']['working']
    client_ready = client_results['realesrgan']['working']
    
    if server_ready:
        print("✅ Serveur: PRÊT (Real-ESRGAN + FFmpeg disponibles)")
    else:
        print("❌ Serveur: NON PRÊT")
        if not server_results['realesrgan']['working']:
            print("   - Real-ESRGAN manquant ou non fonctionnel")
        if not server_results['ffmpeg']['working']:
            print("   - FFmpeg manquant ou non fonctionnel")
    
    if client_ready:
        print("✅ Client: PRÊT (Real-ESRGAN disponible)")
    else:
        print("❌ Client: NON PRÊT")
        if not client_results['realesrgan']['working']:
            print("   - Real-ESRGAN manquant ou non fonctionnel")
    
    print()

def print_installation_instructions():
    """Affiche les instructions d'installation"""
    print("=" * 70)
    print("📋 INSTRUCTIONS D'INSTALLATION")
    print("=" * 70)
    print()
    
    print("🔸 Real-ESRGAN:")
    print("   📥 Télécharger: https://github.com/xinntao/Real-ESRGAN/releases")
    print("   📦 Fichier: realesrgan-ncnn-vulkan-YYYYMMDD-windows.zip")
    print("   📁 Serveur: UpscalingByNetwork/server/realesrgan-ncnn-vulkan/")
    print("   📁 Client:  UpscalingByNetwork/client/windows/realesrgan-ncnn-vulkan/")
    print()
    
    print("🔸 FFmpeg:")
    print("   📥 Télécharger: https://ffmpeg.org/download.html")
    print("   📦 Fichier: ffmpeg-master-latest-win64-gpl.zip")
    print("   📁 Serveur: UpscalingByNetwork/server/ffmpeg/")
    print("   📁 Client:  UpscalingByNetwork/client/windows/ffmpeg/ (optionnel)")
    print()
    
    print("🔸 Structure finale attendue:")
    print("   UpscalingByNetwork/")
    print("   ├── server/")
    print("   │   ├── realesrgan-ncnn-vulkan/")
    print("   │   │   └── realesrgan-ncnn-vulkan.exe")
    print("   │   └── ffmpeg/")
    print("   │       ├── ffmpeg.exe")
    print("   │       └── ffprobe.exe")
    print("   └── client/")
    print("       └── windows/")
    print("           └── realesrgan-ncnn-vulkan/")
    print("               └── realesrgan-ncnn-vulkan.exe")
    print()

def save_results_json(server_results, client_results, structure):
    """Sauvegarde les résultats en JSON"""
    results = {
        'timestamp': subprocess.run(['date'], capture_output=True, text=True).stdout.strip(),
        'project_structure': {
            'project_root': str(structure['project_root']),
            'server_root': str(structure['server_root']),
            'client_root': str(structure['client_root'])
        },
        'server': server_results,
        'client': client_results,
        'summary': {
            'server_ready': server_results['realesrgan']['working'] and server_results['ffmpeg']['working'],
            'client_ready': client_results['realesrgan']['working']
        }
    }
    
    output_file = structure['project_root'] / "executables_check.json"
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str, ensure_ascii=False)
        print(f"📄 Résultats sauvegardés: {output_file}")
    except Exception as e:
        print(f"⚠️  Erreur sauvegarde: {e}")

def main():
    """Fonction principale"""
    print_banner()
    
    # Détection de la structure du projet
    structure = find_project_structure()
    
    if not structure:
        print("❌ Structure de projet non détectée!")
        print("   Exécutez ce script depuis:")
        print("   - La racine du projet (UpscalingByNetwork/)")
        print("   - Le dossier serveur (UpscalingByNetwork/server/)")
        print("   - Le dossier client (UpscalingByNetwork/client/windows/)")
        return 1
    
    print(f"📁 Projet détecté: {structure['project_root']}")
    print(f"🖥️  Serveur: {structure['server_root']}")
    print(f"💻 Client: {structure['client_root']}")
    print()
    
    # Vérification des exécutables
    print("🔍 Recherche des exécutables...")
    print()
    
    server_results = find_executables(structure['server_root'], "serveur")
    client_results = find_executables(structure['client_root'], "client")
    
    # Affichage des résultats
    print_component_status("SERVEUR", server_results)
    print_component_status("CLIENT", client_results)
    
    # Résumé
    print_summary(server_results, client_results)
    
    # Instructions si des éléments manquent
    missing_server = not all(r['working'] for r in server_results.values())
    missing_client = not client_results['realesrgan']['working']
    
    if missing_server or missing_client:
        print_installation_instructions()
    
    # Sauvegarde des résultats
    save_results_json(server_results, client_results, structure)
    
    # Code de retour
    if server_results['realesrgan']['working'] and client_results['realesrgan']['working']:
        print("🎉 Configuration minimale OK - Le système peut fonctionner!")
        return 0
    else:
        print("⚠️  Configuration incomplète - Installez les exécutables manquants")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)