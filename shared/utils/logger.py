"""
Système de logging centralisé pour le serveur et les clients
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, List
from collections import deque


class ColoredFormatter(logging.Formatter):
    """Formatter avec codes couleur pour la console"""

    # Codes couleur ANSI
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Vert
        'WARNING': '\033[33m',  # Jaune
        'ERROR': '\033[31m',    # Rouge
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }

    def format(self, Record):
        """Formate le message avec des couleurs"""
        LevelName = Record.levelname
        if LevelName in self.COLORS:
            Record.levelname = f"{self.COLORS[LevelName]}{LevelName}{self.COLORS['RESET']}"
        return super().format(Record)


class MemoryLogHandler(logging.Handler):
    """
    Handler qui garde les N derniers logs en mémoire pour affichage dans le GUI
    """

    def __init__(self, MaxLogs: int = 100):
        """
        Initialise le handler

        Args:
            MaxLogs: Nombre maximum de logs à garder en mémoire
        """
        super().__init__()
        self.MaxLogs = MaxLogs
        self.LogBuffer = deque(maxlen=MaxLogs)

    def emit(self, Record):
        """
        Ajoute un log au buffer en mémoire

        Args:
            Record: LogRecord à sauvegarder
        """
        try:
            # Formate le log
            Message = self.format(Record)
            # Ajoute au buffer (automatiquement supprime le plus ancien si plein)
            self.LogBuffer.append({
                'time': datetime.fromtimestamp(Record.created).strftime('%H:%M:%S'),
                'level': Record.levelname,
                'message': Record.getMessage(),
                'formatted': Message
            })
        except Exception:
            self.handleError(Record)

    def GetRecentLogs(self, Count: Optional[int] = None) -> List[dict]:
        """
        Récupère les logs récents

        Args:
            Count: Nombre de logs à retourner (None = tous)

        Returns:
            Liste de dictionnaires contenant les logs
        """
        if Count is None:
            return list(self.LogBuffer)
        else:
            # Retourne les Count derniers logs
            return list(self.LogBuffer)[-Count:]

    def Clear(self):
        """Vide le buffer de logs"""
        self.LogBuffer.clear()


class LoggerManager:
    """Gestionnaire centralisé des loggers"""

    _Loggers = {}
    _MemoryHandlers = {}  # Stocke les MemoryHandlers pour chaque logger

    @classmethod
    def GetLogger(cls, Name: str, LogDir: Optional[str] = None,
                  LogFile: Optional[str] = None, ConsoleOutput: bool = True,
                  FileOutput: bool = True, Level: int = logging.INFO,
                  MemoryOutput: bool = False, MaxMemoryLogs: int = 100) -> logging.Logger:
        """
        Récupère ou crée un logger configuré

        Args:
            Name: Nom du logger
            LogDir: Répertoire des logs (défaut: ./logs)
            LogFile: Nom du fichier de log (défaut: Name.log)
            ConsoleOutput: Afficher dans la console
            FileOutput: Écrire dans un fichier
            Level: Niveau de logging
            MemoryOutput: Garder les logs en mémoire pour le GUI
            MaxMemoryLogs: Nombre maximum de logs à garder en mémoire

        Returns:
            Logger configuré
        """
        # Si le logger existe déjà, le retourner
        if Name in cls._Loggers:
            return cls._Loggers[Name]

        # Créer un nouveau logger
        Logger = logging.getLogger(Name)
        Logger.setLevel(Level)
        Logger.propagate = False

        # Éviter les handlers dupliqués
        if Logger.handlers:
            return Logger

        # Format des messages
        DetailedFormat = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        ColoredFormat = ColoredFormatter(
            fmt='%(asctime)s | %(name)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Handler console avec couleurs
        if ConsoleOutput:
            ConsoleHandler = logging.StreamHandler(sys.stdout)
            ConsoleHandler.setLevel(Level)
            ConsoleHandler.setFormatter(ColoredFormat)
            Logger.addHandler(ConsoleHandler)

        # Handler fichier avec rotation
        if FileOutput:
            # Créer le répertoire des logs si nécessaire
            if LogDir is None:
                LogDir = os.path.join(os.getcwd(), "logs")

            os.makedirs(LogDir, exist_ok=True)

            # Nom du fichier de log
            if LogFile is None:
                LogFile = f"{Name}.log"

            LogPath = os.path.join(LogDir, LogFile)

            # Handler avec rotation (10 MB max, 5 backups)
            FileHandler = RotatingFileHandler(
                LogPath,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding='utf-8'
            )
            FileHandler.setLevel(Level)
            FileHandler.setFormatter(DetailedFormat)
            Logger.addHandler(FileHandler)

        # Handler mémoire pour le GUI
        if MemoryOutput:
            MemoryHandler = MemoryLogHandler(MaxLogs=MaxMemoryLogs)
            MemoryHandler.setLevel(Level)
            MemoryHandler.setFormatter(DetailedFormat)
            Logger.addHandler(MemoryHandler)
            cls._MemoryHandlers[Name] = MemoryHandler

        # Stocker le logger
        cls._Loggers[Name] = Logger

        return Logger

    @classmethod
    def SetLevel(cls, Name: str, Level: int):
        """Change le niveau de logging d'un logger existant"""
        if Name in cls._Loggers:
            cls._Loggers[Name].setLevel(Level)
            for Handler in cls._Loggers[Name].handlers:
                Handler.setLevel(Level)

    @classmethod
    def GetRecentLogs(cls, Name: str, Count: Optional[int] = None) -> List[dict]:
        """
        Récupère les logs récents d'un logger

        Args:
            Name: Nom du logger
            Count: Nombre de logs à retourner (None = tous)

        Returns:
            Liste de dictionnaires contenant les logs
        """
        if Name in cls._MemoryHandlers:
            return cls._MemoryHandlers[Name].GetRecentLogs(Count)
        return []

    @classmethod
    def ClearLogs(cls, Name: str):
        """
        Vide le buffer de logs d'un logger

        Args:
            Name: Nom du logger
        """
        if Name in cls._MemoryHandlers:
            cls._MemoryHandlers[Name].Clear()

    @classmethod
    def CloseAll(cls):
        """Ferme tous les loggers"""
        for Logger in cls._Loggers.values():
            for Handler in Logger.handlers:
                Handler.close()
        cls._Loggers.clear()


def GetServerLogger(Level: int = logging.INFO) -> logging.Logger:
    """
    Récupère le logger du serveur

    Args:
        Level: Niveau de logging

    Returns:
        Logger configuré pour le serveur
    """
    return LoggerManager.GetLogger(
        Name="Server",
        LogFile="server.log",
        Level=Level
    )


def GetClientLogger(Level: int = logging.INFO, MemoryOutput: bool = True) -> logging.Logger:
    """
    Récupère le logger du client

    Args:
        Level: Niveau de logging
        MemoryOutput: Active le stockage des logs en mémoire pour le GUI (défaut: True)

    Returns:
        Logger configuré pour le client
    """
    return LoggerManager.GetLogger(
        Name="Client",
        LogFile="client.log",
        Level=Level,
        MemoryOutput=MemoryOutput,
        MaxMemoryLogs=100  # Garde les 100 derniers logs en mémoire
    )


def GetModuleLogger(ModuleName: str, Level: int = logging.INFO) -> logging.Logger:
    """
    Récupère un logger pour un module spécifique

    Args:
        ModuleName: Nom du module
        Level: Niveau de logging

    Returns:
        Logger configuré pour le module
    """
    return LoggerManager.GetLogger(
        Name=ModuleName,
        LogFile=f"{ModuleName}.log",
        Level=Level
    )


# ============================================================================
# HELPERS DE LOGGING
# ============================================================================

def LogException(Logger: logging.Logger, Exception: Exception, Context: str = ""):
    """
    Log une exception avec son contexte

    Args:
        Logger: Logger à utiliser
        Exception: Exception à logger
        Context: Contexte additionnel
    """
    import traceback

    Message = f"Exception: {type(Exception).__name__}: {str(Exception)}"
    if Context:
        Message = f"{Context} - {Message}"

    Logger.error(Message)
    Logger.debug(traceback.format_exc())


def LogMethodCall(Logger: logging.Logger, MethodName: str, **Kwargs):
    """
    Log un appel de méthode avec ses paramètres

    Args:
        Logger: Logger à utiliser
        MethodName: Nom de la méthode
        **Kwargs: Paramètres de la méthode
    """
    ParamsStr = ", ".join([f"{k}={v}" for k, v in Kwargs.items()])
    Logger.debug(f"Calling {MethodName}({ParamsStr})")


def LogPerformance(Logger: logging.Logger, OperationName: str, DurationSeconds: float):
    """
    Log la performance d'une opération

    Args:
        Logger: Logger à utiliser
        OperationName: Nom de l'opération
        DurationSeconds: Durée en secondes
    """
    Logger.info(f"Performance: {OperationName} completed in {DurationSeconds:.2f}s")


# ============================================================================
# DÉCORATEUR DE LOGGING
# ============================================================================

def LoggedMethod(Logger: logging.Logger):
    """
    Décorateur pour logger automatiquement les appels de méthode

    Usage:
        @LoggedMethod(logger)
        def MyMethod(self, arg1, arg2):
            pass
    """
    def Decorator(Func):
        def Wrapper(*Args, **Kwargs):
            FuncName = Func.__name__
            Logger.debug(f"→ Calling {FuncName}")
            try:
                Result = Func(*Args, **Kwargs)
                Logger.debug(f"✓ {FuncName} completed successfully")
                return Result
            except Exception as e:
                Logger.error(f"✗ {FuncName} failed: {type(e).__name__}: {str(e)}")
                raise
        return Wrapper
    return Decorator


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    # Créer un logger de test
    TestLogger = GetModuleLogger("Test", Level=logging.DEBUG)

    # Tester les différents niveaux
    TestLogger.debug("Ceci est un message de debug")
    TestLogger.info("Ceci est un message d'info")
    TestLogger.warning("Ceci est un avertissement")
    TestLogger.error("Ceci est une erreur")
    TestLogger.critical("Ceci est critique")

    # Tester le logging d'exception
    try:
        raise ValueError("Erreur de test")
    except Exception as e:
        LogException(TestLogger, e, "Test exception logging")

    # Tester le logging de performance
    import time
    StartTime = time.time()
    time.sleep(0.1)
    LogPerformance(TestLogger, "Test operation", time.time() - StartTime)

    # Fermer tous les loggers
    LoggerManager.CloseAll()
