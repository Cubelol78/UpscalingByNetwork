"""
Outils de maintenance pour UpscalingByNetwork
UpscalingByNetwork/scripts/maintenance.py
"""

import os
import sys
import argparse
import shutil
import json
import time
from pathlib import Path
from typing import List, Dict, Any
import logging

# Ajout du projet au path
sys.path.insert(0, str(Path(__file__).parent.parent))

class MaintenanceTool:
    """Outil de maintenance pour UpscalingByNetwork"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.setup_logging()
        
        # Dossiers principaux
        self.server_work = self.project_root / "server_work"
        self.client_work = self.project_root / "client_work"
        self.logs_dir = self.project_root / "logs"
        self.temp_dirs = [
            self.server_work / "temp",
            self.client_work / "temp",
            self.project_root / "build",
            self.project_root / "dist"
        ]
    
    def setup_logging(self):
        """Configure le logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
    
    def cleanup_temp_files(self, dry_run: bool = False) -> Dict[str, Any]:
        """Nettoie les fichiers temporaires"""
        self.logger.info("🧹 Nettoyage des fichiers temporaires...")
        
        stats = {
            'folders_cleaned': 0,
            'files_deleted': 0,
            'space_freed': 0,
            'errors': []
        }
        
        for temp_dir in self.temp_dirs:
            if not temp_dir.exists():
                continue
            
            try:
                # Calcul de l'espace utilisé
                dir_size = self._get_directory_size(temp_dir)
                
                if dry_run:
                    self.logger.info(f"   [DRY RUN] {temp_dir}: {self._format_size(dir_size)}")
                    stats['space_freed'] += dir_size
                    stats['folders_cleaned'] += 1
                else:
                    file_count = len(list(temp_dir.rglob('*')))
                    shutil.rmtree(temp_dir)
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    
                    self.logger.info(f"   ✅ {temp_dir}: {file_count} fichiers, {self._format_size(dir_size)}")
                    stats['files_deleted'] += file_count
                    stats['space_freed'] += dir_size
                    stats['folders_cleaned'] += 1
                    
            except Exception as e:
                error_msg = f"Erreur nettoyage {temp_dir}: {e}"
                self.logger.error(f"   ❌ {error_msg}")
                stats['errors'].append(error_msg)
        
        self.logger.info(f"✅ Nettoyage terminé: {stats['folders_cleaned']} dossiers, "
                        f"{stats['files_deleted']} fichiers, {self._format_size(stats['space_freed'])} libérés")
        
        return stats
    
    def cleanup_old_logs(self, days: int = 30, dry_run: bool = False) -> Dict[str, Any]:
        """Nettoie les anciens logs"""
        self.logger.info(f"📋 Nettoyage des logs de plus de {days} jours...")
        
        stats = {
            'files_deleted': 0,
            'space_freed': 0,
            'errors': []
        }
        
        cutoff_time = time.time() - (days * 24 * 3600)
        
        log_dirs = [
            self.logs_dir,
            self.server_work / "logs" if (self.server_work / "logs").exists() else None,
            self.client_work / "logs" if (self.client_work / "logs").exists() else None
        ]
        
        for log_dir in filter(None, log_dirs):
            if not log_dir.exists():
                continue
            
            for log_file in log_dir.glob("*.log*"):
                try:
                    if log_file.stat().st_mtime < cutoff_time:
                        file_size = log_file.stat().st_size
                        
                        if dry_run:
                            self.logger.info(f"   [DRY RUN] {log_file.name}: {self._format_size(file_size)}")
                        else:
                            log_file.unlink()
                            self.logger.info(f"   ✅ {log_file.name}: {self._format_size(file_size)}")
                        
                        stats['files_deleted'] += 1
                        stats['space_freed'] += file_size
                        
                except Exception as e:
                    error_msg = f"Erreur suppression {log_file}: {e}"
                    self.logger.error(f"   ❌ {error_msg}")
                    stats['errors'].append(error_msg)
        
        self.logger.info(f"✅ Logs nettoyés: {stats['files_deleted']} fichiers, "
                        f"{self._format_size(stats['space_freed'])} libérés")
        
        return stats
    
    def verify_installation(self) -> Dict[str, Any]:
        """Vérifie l'intégrité de l'installation"""
        self.logger.info("🔍 Vérification de l'installation...")
        
        checks = {
            'python_modules': self._check_python_modules(),
            'executables': self._check_executables(),
            'directories': self._check_directories(),
            'permissions': self._check_permissions()
        }
        
        # Résumé
        all_passed = all(check['status'] for check in checks.values())
        
        if all_passed:
            self.logger.info("✅ Installation vérifiée avec succès")
        else:
            self.logger.warning("⚠️  Problèmes détectés dans l'installation")
        
        return {
            'status': all_passed,
            'checks': checks
        }
    
    def _check_python_modules(self) -> Dict[str, Any]:
        """Vérifie les modules Python"""
        required_modules = [
            'websockets', 'cryptography', 'psutil', 'PyQt5', 'qasync'
        ]
        
        missing = []
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing.append(module)
        
        return {
            'status': len(missing) == 0,
            'missing_modules': missing,
            'message': f"Modules manquants: {missing}" if missing else "Tous les modules présents"
        }
    
    def _check_executables(self) -> Dict[str, Any]:
        """Vérifie les exécutables"""
        executables = {
            'FFmpeg serveur': self.project_root / "server" / "ffmpeg" / "ffmpeg.exe",
            'Real-ESRGAN serveur': self.project_root / "server" / "realesrgan-ncnn-vulkan" / "realesrgan-ncnn-vulkan.exe",
            'Real-ESRGAN client': self.project_root / "client" / "windows" / "realesrgan-ncnn-vulkan" / "realesrgan-ncnn-vulkan.exe"
        }
        
        missing = []
        for name, path in executables.items():
            if not path.exists():
                missing.append(f"{name} ({path})")
        
        return {
            'status': len(missing) == 0,
            'missing_executables': missing,
            'message': f"Exécutables manquants: {missing}" if missing else "Tous les exécutables présents"
        }
    
    def _check_directories(self) -> Dict[str, Any]:
        """Vérifie les dossiers"""
        required_dirs = [
            self.project_root / "server",
            self.project_root / "client",
            self.project_root / "shared"
        ]
        
        missing = []
        for directory in required_dirs:
            if not directory.exists():
                missing.append(str(directory))
        
        return {
            'status': len(missing) == 0,
            'missing_directories': missing,
            'message': f"Dossiers manquants: {missing}" if missing else "Tous les dossiers présents"
        }
    
    def _check_permissions(self) -> Dict[str, Any]:
        """Vérifie les permissions"""
        test_dirs = [
            self.server_work,
            self.client_work,
            self.logs_dir
        ]
        
        permission_issues = []
        
        for test_dir in test_dirs:
            try:
                test_dir.mkdir(parents=True, exist_ok=True)
                test_file = test_dir / "permission_test.tmp"
                test_file.write_text("test")
                test_file.unlink()
            except Exception as e:
                permission_issues.append(f"{test_dir}: {e}")
        
        return {
            'status': len(permission_issues) == 0,
            'permission_issues': permission_issues,
            'message': f"Problèmes de permissions: {permission_issues}" if permission_issues else "Permissions OK"
        }
    
    def backup_configuration(self, backup_path: str = None) -> str:
        """Sauvegarde la configuration"""
        if not backup_path:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = f"backup_config_{timestamp}.json"
        
        self.logger.info(f"💾 Sauvegarde de la configuration vers {backup_path}...")
        
        config_data = {
            'timestamp': time.time(),
            'version': '1.0.0',
            'server_config': self._load_config('server'),
            'client_config': self._load_config('client'),
            'system_info': self._get_system_info()
        }
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, default=str)
        
        self.logger.info(f"✅ Configuration sauvegardée dans {backup_path}")
        return backup_path
    
    def restore_configuration(self, backup_path: str) -> bool:
        """Restaure la configuration"""
        self.logger.info(f"🔄 Restauration de la configuration depuis {backup_path}...")
        
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Restauration des configurations
            if 'server_config' in config_data:
                self._save_config('server', config_data['server_config'])
            
            if 'client_config' in config_data:
                self._save_config('client', config_data['client_config'])
            
            self.logger.info("✅ Configuration restaurée avec succès")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erreur restauration: {e}")
            return False
    
    def generate_system_report(self, output_path: str = None) -> str:
        """Génère un rapport système complet"""
        if not output_path:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = f"system_report_{timestamp}.json"
        
        self.logger.info(f"📊 Génération du rapport système...")
        
        report = {
            'timestamp': time.time(),
            'system_info': self._get_system_info(),
            'installation_check': self.verify_installation(),
            'disk_usage': self._get_disk_usage(),
            'process_info': self._get_process_info(),
            'configuration': {
                'server': self._load_config('server'),
                'client': self._load_config('client')
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
        
        self.logger.info(f"✅ Rapport généré: {output_path}")
        return output_path
    
    def _load_config(self, component: str) -> Dict[str, Any]:
        """Charge la configuration d'un composant"""
        config_file = self.project_root / "config" / f"{component}_config.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Erreur lecture config {component}: {e}")
        
        return {}
    
    def _save_config(self, component: str, config: Dict[str, Any]):
        """Sauvegarde la configuration d'un composant"""
        config_dir = self.project_root / "config"
        config_dir.mkdir(exist_ok=True)
        
        config_file = config_dir / f"{component}_config.json"
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, default=str)
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Récupère les informations système"""
        try:
            import platform
            import psutil
            
            return {
                'platform': platform.system(),
                'platform_version': platform.version(),
                'architecture': platform.architecture()[0],
                'python_version': platform.python_version(),
                'cpu_count': psutil.cpu_count(),
                'memory_total': psutil.virtual_memory().total,
                'disk_total': psutil.disk_usage('.').total
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _get_disk_usage(self) -> Dict[str, Any]:
        """Calcule l'utilisation disque du projet"""
        usage = {}
        
        for name, directory in [
            ('server_work', self.server_work),
            ('client_work', self.client_work),
            ('logs', self.logs_dir),
            ('total_project', self.project_root)
        ]:
            if directory.exists():
                size = self._get_directory_size(directory)
                usage[name] = {
                    'size_bytes': size,
                    'size_formatted': self._format_size(size)
                }
        
        return usage
    
    def _get_process_info(self) -> Dict[str, Any]:
        """Récupère les informations sur les processus actifs"""
        try:
            import psutil
            
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'UpscalingByNetwork' in cmdline or 'server_main.py' in cmdline or 'client_main.py' in cmdline:
                        processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cmdline': cmdline
                        })
                except Exception:
                    continue
            
            return {'active_processes': processes}
            
        except Exception as e:
            return {'error': str(e)}
    
    def _get_directory_size(self, directory: Path) -> int:
        """Calcule la taille d'un dossier"""
        total_size = 0
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
        except Exception:
            pass
        return total_size
    
    def _format_size(self, size_bytes: int) -> str:
        """Formate une taille en bytes"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(
        description="Outil de maintenance UpscalingByNetwork",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s cleanup               # Nettoie les fichiers temporaires
  %(prog)s cleanup --dry-run     # Aperçu du nettoyage
  %(prog)s verify                # Vérifie l'installation
  %(prog)s backup                # Sauvegarde la configuration
  %(prog)s report                # Génère un rapport système
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')
    
    # Commande cleanup
    cleanup_parser = subparsers.add_parser('cleanup', help='Nettoie les fichiers temporaires')
    cleanup_parser.add_argument('--dry-run', action='store_true', help='Aperçu sans suppression')
    cleanup_parser.add_argument('--logs', type=int, default=30, help='Nettoie les logs de plus de N jours')
    cleanup_parser.add_argument('--all', action='store_true', help='Nettoyage complet')
    
    # Commande verify
    verify_parser = subparsers.add_parser('verify', help='Vérifie l\'installation')
    
    # Commande backup
    backup_parser = subparsers.add_parser('backup', help='Sauvegarde la configuration')
    backup_parser.add_argument('--output', help='Fichier de sauvegarde')
    
    # Commande restore
    restore_parser = subparsers.add_parser('restore', help='Restaure la configuration')
    restore_parser.add_argument('backup_file', help='Fichier de sauvegarde')
    
    # Commande report
    report_parser = subparsers.add_parser('report', help='Génère un rapport système')
    report_parser.add_argument('--output', help='Fichier de rapport')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    tool = MaintenanceTool()
    
    try:
        if args.command == 'cleanup':
            if args.all:
                tool.cleanup_temp_files(args.dry_run)
                tool.cleanup_old_logs(args.logs, args.dry_run)
            else:
                tool.cleanup_temp_files(args.dry_run)
        
        elif args.command == 'verify':
            result = tool.verify_installation()
            if not result['status']:
                sys.exit(1)
        
        elif args.command == 'backup':
            tool.backup_configuration(args.output)
        
        elif args.command == 'restore':
            success = tool.restore_configuration(args.backup_file)
            if not success:
                sys.exit(1)
        
        elif args.command == 'report':
            tool.generate_system_report(args.output)
    
    except KeyboardInterrupt:
        print("\nOpération annulée par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"Erreur: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

