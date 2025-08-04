# UpscalingByNetwork/tests/run_tests.py

"""
Script d'exécution des tests
UpscalingByNetwork/tests/run_tests.py
"""

import sys
import subprocess
from pathlib import Path

def run_tests():
    """Exécute tous les tests"""
    test_dir = Path(__file__).parent
    project_root = test_dir.parent
    
    print("🧪 Exécution des tests UpscalingByNetwork")
    print("=" * 50)
    
    # Ajout du projet au PYTHONPATH
    sys.path.insert(0, str(project_root))
    
    # Commande pytest
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_dir),
        "-v",
        "--tb=short",
        "--color=yes",
        "--durations=10"
    ]
    
    print(f"Commande: {' '.join(cmd)}")
    print()
    
    # Exécution
    result = subprocess.run(cmd, cwd=project_root)
    
    if result.returncode == 0:
        print("\n✅ Tous les tests sont passés avec succès!")
    else:
        print(f"\n❌ Tests échoués (code de retour: {result.returncode})")
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(run_tests())