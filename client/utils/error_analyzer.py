"""
Analyseur d'erreurs Real-ESRGAN
Détecte les types d'erreurs et génère des suggestions pour l'utilisateur
"""

from typing import Dict, List, Optional
from shared.utils.logger import GetModuleLogger


class UpscalingErrorAnalyzer:
    """Analyse les erreurs Real-ESRGAN et génère des suggestions"""

    # Patterns d'erreurs critiques (nécessitent déconnexion)
    CRITICAL_PATTERNS = [
        {
            "patterns": [
                "vkAllocateMemory failed",
                "out of memory",
                "CUDA out of memory",
                "failed to allocate",
                "memory allocation failed"
            ],
            "type": "gpu_memory",
            "message": "Memoire GPU insuffisante",
            "suggestions": [
                "Reduire le Tile Size (ex: 128 ou 192)",
                "Reduire les threads de traitement a 1 ou 2",
                "Fermer les autres applications utilisant le GPU"
            ]
        },
        {
            "patterns": [
                "failed to create pipeline",
                "vkCreateComputePipeline",
                "pipeline creation failed"
            ],
            "type": "gpu_init",
            "message": "Erreur d'initialisation GPU",
            "suggestions": [
                "Verifier que les drivers GPU sont a jour",
                "Essayer un autre GPU dans les parametres",
                "Reduire le Tile Size"
            ]
        },
        {
            "patterns": [
                "no vulkan device",
                "vulkan driver",
                "failed to find vulkan",
                "vulkan not found"
            ],
            "type": "gpu_driver",
            "message": "Drivers Vulkan non trouves",
            "suggestions": [
                "Installer/mettre a jour les drivers GPU",
                "Verifier que Vulkan est supporte par votre carte graphique"
            ]
        },
        {
            "patterns": [
                "invalid model",
                "model not found",
                "failed to load model"
            ],
            "type": "model_error",
            "message": "Erreur de modele Real-ESRGAN",
            "suggestions": [
                "Verifier que le modele selectionne est disponible",
                "Reinstaller Real-ESRGAN"
            ]
        }
    ]

    def __init__(self):
        self.Logger = GetModuleLogger("ErrorAnalyzer")

    def Analyze(self, ErrorOutput: str) -> Dict:
        """
        Analyse une sortie d'erreur Real-ESRGAN et retourne les informations

        Args:
            ErrorOutput: Sortie stderr de Real-ESRGAN

        Returns:
            Dict avec:
                - is_critical: bool - True si l'erreur nécessite déconnexion
                - type: str - Type d'erreur (gpu_memory, gpu_init, etc.)
                - message: str - Message utilisateur
                - suggestions: List[str] - Suggestions pour corriger
                - raw_error: str - Erreur brute
        """
        if not ErrorOutput:
            return {"is_critical": False, "raw_error": ""}

        ErrorLower = ErrorOutput.lower()

        for Pattern in self.CRITICAL_PATTERNS:
            if any(p.lower() in ErrorLower for p in Pattern["patterns"]):
                self.Logger.info(f"Erreur critique detectee: {Pattern['type']}")
                return {
                    "is_critical": True,
                    "type": Pattern["type"],
                    "message": Pattern["message"],
                    "suggestions": Pattern["suggestions"],
                    "raw_error": ErrorOutput
                }

        # Erreur non reconnue = pas critique, le client peut continuer
        self.Logger.debug(f"Erreur non critique: {ErrorOutput[:100]}...")
        return {
            "is_critical": False,
            "type": "unknown",
            "message": "Erreur d'upscaling",
            "suggestions": [],
            "raw_error": ErrorOutput
        }

    def FormatErrorMessage(self, ErrorInfo: Dict) -> str:
        """
        Formate les informations d'erreur en message lisible

        Args:
            ErrorInfo: Dictionnaire retourné par Analyze()

        Returns:
            Message formaté pour affichage
        """
        if not ErrorInfo.get("is_critical"):
            return ErrorInfo.get("raw_error", "Erreur inconnue")

        Lines = [ErrorInfo.get("message", "Erreur")]
        Lines.append("")

        Suggestions = ErrorInfo.get("suggestions", [])
        if Suggestions:
            Lines.append("Suggestions:")
            for Suggestion in Suggestions:
                Lines.append(f"  - {Suggestion}")

        return "\n".join(Lines)


# Instance globale pour réutilisation
_AnalyzerInstance: Optional[UpscalingErrorAnalyzer] = None


def GetErrorAnalyzer() -> UpscalingErrorAnalyzer:
    """Retourne l'instance singleton de l'analyseur d'erreurs"""
    global _AnalyzerInstance
    if _AnalyzerInstance is None:
        _AnalyzerInstance = UpscalingErrorAnalyzer()
    return _AnalyzerInstance
