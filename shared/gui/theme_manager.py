"""
Gestionnaire de thème adaptatif pour l'interface graphique
Détecte les préférences système et applique le thème correspondant
Supporte Windows, Linux (GNOME/KDE) et macOS
"""

import os
import sys
import subprocess
from typing import Optional

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QPalette, QColor

from shared.utils.logger import GetModuleLogger


class ThemeManager(QObject):
    """Gestionnaire de thème avec détection système et mise à jour en temps réel"""

    # Signal émis quand le thème change
    ThemeChanged = pyqtSignal(str)

    # Constantes de thème
    THEME_LIGHT = "light"
    THEME_DARK = "dark"
    THEME_AUTO = "auto"

    # Palettes de couleurs
    LightPalette = {
        "background": "#FFFFFF",
        "surface": "#F5F5F5",
        "surface_variant": "#EEEEEE",
        "primary": "#4CAF50",
        "primary_hover": "#45A049",
        "primary_pressed": "#3D8B40",
        "danger": "#F44336",
        "danger_hover": "#E53935",
        "danger_pressed": "#D32F2F",
        "warning": "#FF9800",
        "warning_hover": "#FB8C00",
        "info": "#2196F3",
        "info_hover": "#1E88E5",
        "text": "#212121",
        "text_secondary": "#666666",
        "text_disabled": "#9E9E9E",
        "border": "#E0E0E0",
        "border_focus": "#4CAF50",
        "table_alt": "#FAFAFA",
        "table_header": "#F0F0F0",
        "scrollbar": "#CCCCCC",
        "scrollbar_hover": "#AAAAAA",
        "tab_active": "#FFFFFF",
        "tab_inactive": "#E8E8E8",
        "input_background": "#FFFFFF",
        "selection": "#4CAF50",
        "selection_text": "#FFFFFF",
    }

    DarkPalette = {
        "background": "#1E1E1E",
        "surface": "#2D2D2D",
        "surface_variant": "#383838",
        "primary": "#66BB6A",
        "primary_hover": "#81C784",
        "primary_pressed": "#4CAF50",
        "danger": "#EF5350",
        "danger_hover": "#E57373",
        "danger_pressed": "#F44336",
        "warning": "#FFA726",
        "warning_hover": "#FFB74D",
        "info": "#42A5F5",
        "info_hover": "#64B5F6",
        "text": "#E0E0E0",
        "text_secondary": "#9E9E9E",
        "text_disabled": "#616161",
        "border": "#424242",
        "border_focus": "#66BB6A",
        "table_alt": "#383838",
        "table_header": "#424242",
        "scrollbar": "#555555",
        "scrollbar_hover": "#666666",
        "tab_active": "#2D2D2D",
        "tab_inactive": "#252525",
        "input_background": "#383838",
        "selection": "#66BB6A",
        "selection_text": "#1E1E1E",
    }

    # Instance singleton
    _Instance: Optional['ThemeManager'] = None

    def __init__(self, App: QApplication):
        """
        Initialise le gestionnaire de thème

        Args:
            App: Instance de QApplication
        """
        super().__init__()
        self.Logger = GetModuleLogger("ThemeManager")
        self.App = App
        self.CurrentTheme = None
        self.UserPreference = self.THEME_AUTO
        self._LastSystemTheme = None

        # Timer pour vérifier les changements de thème système
        self.CheckTimer = QTimer()
        self.CheckTimer.timeout.connect(self._CheckThemeChange)
        self.CheckTimer.start(5000)  # Vérifier toutes les 5 secondes

        # Appliquer le thème initial
        self._ApplyCurrentTheme()

        # Stocker l'instance singleton
        ThemeManager._Instance = self

        self.Logger.info(f"ThemeManager initialisé, thème: {self.CurrentTheme}")

    @classmethod
    def GetInstance(cls) -> Optional['ThemeManager']:
        """Récupère l'instance singleton du ThemeManager"""
        return cls._Instance

    def SetUserPreference(self, Preference: str):
        """
        Définit la préférence utilisateur pour le thème

        Args:
            Preference: "auto", "light" ou "dark"
        """
        if Preference not in [self.THEME_AUTO, self.THEME_LIGHT, self.THEME_DARK]:
            self.Logger.warning(f"Préférence invalide: {Preference}, utilisation de 'auto'")
            Preference = self.THEME_AUTO

        OldPreference = self.UserPreference
        self.UserPreference = Preference

        if OldPreference != Preference:
            self.Logger.info(f"Préférence thème changée: {OldPreference} -> {Preference}")
            self._ApplyCurrentTheme()

    def GetUserPreference(self) -> str:
        """Récupère la préférence utilisateur actuelle"""
        return self.UserPreference

    def GetCurrentTheme(self) -> str:
        """Récupère le thème actuellement appliqué"""
        return self.CurrentTheme

    def GetPalette(self, ThemeName: str = None) -> dict:
        """
        Récupère la palette de couleurs pour un thème

        Args:
            ThemeName: Nom du thème (si None, utilise le thème actuel)

        Returns:
            Dictionnaire de couleurs
        """
        if ThemeName is None:
            ThemeName = self.CurrentTheme

        if ThemeName == self.THEME_DARK:
            return self.DarkPalette.copy()
        return self.LightPalette.copy()

    def GetColor(self, ColorName: str) -> str:
        """
        Récupère une couleur spécifique du thème actuel

        Args:
            ColorName: Nom de la couleur (ex: "primary", "background")

        Returns:
            Code couleur hexadécimal
        """
        Palette = self.GetPalette()
        return Palette.get(ColorName, "#000000")

    @staticmethod
    def DetectSystemTheme() -> str:
        """
        Détecte le thème système actuel

        Returns:
            "light" ou "dark"
        """
        Logger = GetModuleLogger("ThemeManager")

        try:
            if sys.platform == "win32":
                # Windows: Lecture du registre
                import winreg
                try:
                    Key = winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                    )
                    Value, _ = winreg.QueryValueEx(Key, "AppsUseLightTheme")
                    winreg.CloseKey(Key)
                    return ThemeManager.THEME_LIGHT if Value == 1 else ThemeManager.THEME_DARK
                except Exception as e:
                    Logger.debug(f"Impossible de lire le registre Windows: {e}")
                    return ThemeManager.THEME_LIGHT

            elif sys.platform == "darwin":
                # macOS: Commande defaults
                try:
                    Result = subprocess.run(
                        ["defaults", "read", "-g", "AppleInterfaceStyle"],
                        capture_output=True,
                        text=True
                    )
                    if "Dark" in Result.stdout:
                        return ThemeManager.THEME_DARK
                    return ThemeManager.THEME_LIGHT
                except Exception as e:
                    Logger.debug(f"Impossible de détecter le thème macOS: {e}")
                    return ThemeManager.THEME_LIGHT

            else:
                # Linux: Essayer plusieurs méthodes
                return ThemeManager._DetectLinuxTheme()

        except Exception as e:
            Logger.error(f"Erreur lors de la détection du thème système: {e}")
            return ThemeManager.THEME_LIGHT

    @staticmethod
    def _DetectLinuxTheme() -> str:
        """
        Détecte le thème sur Linux (GNOME, KDE, etc.)

        Returns:
            "light" ou "dark"
        """
        Logger = GetModuleLogger("ThemeManager")

        # Méthode 1: GNOME/GTK via gsettings
        try:
            Result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True,
                text=True
            )
            if "dark" in Result.stdout.lower():
                return ThemeManager.THEME_DARK
            elif "light" in Result.stdout.lower() or "default" in Result.stdout.lower():
                return ThemeManager.THEME_LIGHT
        except Exception:
            pass

        # Méthode 2: GTK_THEME environment variable
        GtkTheme = os.environ.get("GTK_THEME", "")
        if "dark" in GtkTheme.lower():
            return ThemeManager.THEME_DARK

        # Méthode 3: KDE via kdeglobals
        try:
            KdeConfigPath = os.path.expanduser("~/.config/kdeglobals")
            if os.path.exists(KdeConfigPath):
                with open(KdeConfigPath, 'r') as f:
                    Content = f.read()
                    if "dark" in Content.lower():
                        return ThemeManager.THEME_DARK
        except Exception:
            pass

        # Méthode 4: Vérifier le thème GTK actuel
        try:
            Result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                capture_output=True,
                text=True
            )
            if "dark" in Result.stdout.lower():
                return ThemeManager.THEME_DARK
        except Exception:
            pass

        # Par défaut: thème clair
        return ThemeManager.THEME_LIGHT

    def _CheckThemeChange(self):
        """Vérifie si le thème système a changé (appelé par le timer)"""
        if self.UserPreference != self.THEME_AUTO:
            return

        SystemTheme = self.DetectSystemTheme()

        if SystemTheme != self._LastSystemTheme:
            self._LastSystemTheme = SystemTheme
            if self.CurrentTheme != SystemTheme:
                self.Logger.info(f"Thème système changé: {self.CurrentTheme} -> {SystemTheme}")
                self._ApplyCurrentTheme()

    def _ApplyCurrentTheme(self):
        """Applique le thème actuel à l'application"""
        # Déterminer le thème à appliquer
        if self.UserPreference == self.THEME_AUTO:
            NewTheme = self.DetectSystemTheme()
        else:
            NewTheme = self.UserPreference

        # Mettre à jour l'état
        OldTheme = self.CurrentTheme
        self.CurrentTheme = NewTheme
        self._LastSystemTheme = self.DetectSystemTheme()

        # Générer et appliquer le stylesheet
        Stylesheet = self._GenerateStylesheet(NewTheme)
        self.App.setStyleSheet(Stylesheet)

        # Émettre le signal de changement
        if OldTheme != NewTheme:
            self.ThemeChanged.emit(NewTheme)
            self.Logger.info(f"Thème appliqué: {NewTheme}")

    def _GenerateStylesheet(self, ThemeName: str) -> str:
        """
        Génère le stylesheet QSS complet pour un thème

        Args:
            ThemeName: "light" ou "dark"

        Returns:
            Stylesheet QSS
        """
        P = self.DarkPalette if ThemeName == self.THEME_DARK else self.LightPalette

        return f"""
/* ========================================
   THÈME: {ThemeName.upper()}
   ======================================== */

/* === Base === */
QMainWindow, QWidget {{
    background-color: {P['background']};
    color: {P['text']};
    font-family: "Segoe UI", "Ubuntu", "Roboto", sans-serif;
}}

/* === GroupBox === */
QGroupBox {{
    background-color: {P['surface']};
    border: 1px solid {P['border']};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: {P['text']};
}}

/* === Labels === */
QLabel {{
    color: {P['text']};
    background-color: transparent;
}}

/* === Boutons === */
QPushButton {{
    background-color: {P['surface_variant']};
    color: {P['text']};
    border: 1px solid {P['border']};
    border-radius: 4px;
    padding: 6px 16px;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {P['border']};
    border-color: {P['border_focus']};
}}

QPushButton:pressed {{
    background-color: {P['surface']};
}}

QPushButton:disabled {{
    background-color: {P['surface']};
    color: {P['text_disabled']};
    border-color: {P['border']};
}}

/* === Boutons Primary (vert) === */
QPushButton[class="primary"], QPushButton#ConnectButton, QPushButton#StartButton {{
    background-color: {P['primary']};
    color: white;
    border: none;
    font-weight: bold;
}}

QPushButton[class="primary"]:hover, QPushButton#ConnectButton:hover, QPushButton#StartButton:hover {{
    background-color: {P['primary_hover']};
}}

QPushButton[class="primary"]:pressed, QPushButton#ConnectButton:pressed, QPushButton#StartButton:pressed {{
    background-color: {P['primary_pressed']};
}}

/* === Boutons Danger (rouge) === */
QPushButton[class="danger"], QPushButton#DisconnectButton, QPushButton#StopButton {{
    background-color: {P['danger']};
    color: white;
    border: none;
    font-weight: bold;
}}

QPushButton[class="danger"]:hover, QPushButton#DisconnectButton:hover, QPushButton#StopButton:hover {{
    background-color: {P['danger_hover']};
}}

QPushButton[class="danger"]:pressed, QPushButton#DisconnectButton:pressed, QPushButton#StopButton:pressed {{
    background-color: {P['danger_pressed']};
}}

/* === Boutons Warning (orange) === */
QPushButton[class="warning"] {{
    background-color: {P['warning']};
    color: white;
    border: none;
    font-weight: bold;
}}

QPushButton[class="warning"]:hover {{
    background-color: {P['warning_hover']};
}}

/* === Boutons Info (bleu) === */
QPushButton[class="info"] {{
    background-color: {P['info']};
    color: white;
    border: none;
    font-weight: bold;
}}

QPushButton[class="info"]:hover {{
    background-color: {P['info_hover']};
}}

/* === Champs de saisie === */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {P['input_background']};
    color: {P['text']};
    border: 1px solid {P['border']};
    border-radius: 4px;
    padding: 6px;
    selection-background-color: {P['selection']};
    selection-color: {P['selection_text']};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {P['border_focus']};
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {P['surface']};
    color: {P['text_disabled']};
}}

/* === ComboBox === */
QComboBox {{
    background-color: {P['input_background']};
    color: {P['text']};
    border: 1px solid {P['border']};
    border-radius: 4px;
    padding: 6px;
    min-height: 20px;
}}

QComboBox:hover {{
    border-color: {P['border_focus']};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background-color: {P['surface']};
    color: {P['text']};
    border: 1px solid {P['border']};
    selection-background-color: {P['selection']};
    selection-color: {P['selection_text']};
}}

/* === Tables === */
QTableWidget, QTableView {{
    background-color: {P['background']};
    alternate-background-color: {P['table_alt']};
    color: {P['text']};
    border: 1px solid {P['border']};
    gridline-color: {P['border']};
    selection-background-color: {P['selection']};
    selection-color: {P['selection_text']};
}}

QTableWidget::item, QTableView::item {{
    padding: 5px;
}}

QHeaderView::section {{
    background-color: {P['table_header']};
    color: {P['text']};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {P['border']};
    font-weight: bold;
}}

/* === Onglets === */
QTabWidget::pane {{
    border: 1px solid {P['border']};
    border-top: none;
    background-color: {P['background']};
}}

QTabBar::tab {{
    background-color: {P['tab_inactive']};
    color: {P['text_secondary']};
    border: 1px solid {P['border']};
    border-bottom: none;
    padding: 8px 16px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {P['tab_active']};
    color: {P['text']};
    border-bottom: 2px solid {P['primary']};
}}

QTabBar::tab:hover:!selected {{
    background-color: {P['surface']};
}}

/* === TextEdit / PlainTextEdit === */
QTextEdit, QPlainTextEdit {{
    background-color: {P['input_background']};
    color: {P['text']};
    border: 1px solid {P['border']};
    border-radius: 4px;
    selection-background-color: {P['selection']};
    selection-color: {P['selection_text']};
}}

/* === ProgressBar === */
QProgressBar {{
    background-color: {P['surface']};
    border: 1px solid {P['border']};
    border-radius: 4px;
    text-align: center;
    color: {P['text']};
}}

QProgressBar::chunk {{
    background-color: {P['primary']};
    border-radius: 3px;
}}

/* === ScrollBar Vertical === */
QScrollBar:vertical {{
    background-color: {P['surface']};
    width: 12px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {P['scrollbar']};
    min-height: 30px;
    border-radius: 6px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {P['scrollbar_hover']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* === ScrollBar Horizontal === */
QScrollBar:horizontal {{
    background-color: {P['surface']};
    height: 12px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: {P['scrollbar']};
    min-width: 30px;
    border-radius: 6px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {P['scrollbar_hover']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* === Slider === */
QSlider::groove:horizontal {{
    background-color: {P['surface_variant']};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: {P['primary']};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {P['primary_hover']};
}}

/* === CheckBox === */
QCheckBox {{
    color: {P['text']};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {P['border']};
    border-radius: 3px;
    background-color: {P['input_background']};
}}

QCheckBox::indicator:checked {{
    background-color: {P['primary']};
    border-color: {P['primary']};
}}

QCheckBox::indicator:hover {{
    border-color: {P['border_focus']};
}}

/* === RadioButton === */
QRadioButton {{
    color: {P['text']};
    spacing: 8px;
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {P['border']};
    border-radius: 10px;
    background-color: {P['input_background']};
}}

QRadioButton::indicator:checked {{
    background-color: {P['primary']};
    border-color: {P['primary']};
}}

/* === StatusBar === */
QStatusBar {{
    background-color: {P['surface']};
    color: {P['text_secondary']};
    border-top: 1px solid {P['border']};
}}

/* === Status Label (indicateur running/stopped) === */
QLabel#StatusLabel {{
    font-weight: bold;
    font-size: 14px;
}}

QLabel#StatusLabel[status="running"] {{
    color: {P['primary']};
}}

QLabel#StatusLabel[status="stopped"] {{
    color: {P['danger']};
}}

/* === Labels d'indication (notes, hints) === */
QLabel[class="hint"] {{
    color: {P['text_secondary']};
    font-style: italic;
    font-size: 10px;
}}

QLabel[class="hint-warning"] {{
    color: {P['warning']};
    font-style: italic;
    font-size: 10px;
}}

QLabel[class="hint-success"] {{
    color: {P['primary']};
    font-style: italic;
}}

QLabel[class="hint-danger"] {{
    color: {P['danger']};
    font-style: italic;
}}

/* === Labels de statistiques === */
QLabel[class="stat-value"] {{
    color: {P['info']};
}}

QLabel[class="stat-desc"] {{
    color: {P['text_secondary']};
}}

/* === Menu === */
QMenuBar {{
    background-color: {P['surface']};
    color: {P['text']};
}}

QMenuBar::item:selected {{
    background-color: {P['selection']};
    color: {P['selection_text']};
}}

QMenu {{
    background-color: {P['surface']};
    color: {P['text']};
    border: 1px solid {P['border']};
}}

QMenu::item:selected {{
    background-color: {P['selection']};
    color: {P['selection_text']};
}}

/* === ToolTip === */
QToolTip {{
    background-color: {P['surface']};
    color: {P['text']};
    border: 1px solid {P['border']};
    padding: 4px;
}}

/* === Dialog === */
QDialog {{
    background-color: {P['background']};
}}

/* === CollapsiblePanel === */
#CollapsibleHeader {{
    background-color: {P['surface']};
    border: 1px solid {P['border']};
    border-radius: 6px 6px 0 0;
}}

#CollapsibleHeader:hover {{
    background-color: {P['surface_variant']};
}}

#CollapsibleArrow {{
    color: {P['text_secondary']};
    font-size: 10px;
}}

#CollapsibleTitle {{
    color: {P['text']};
}}

#CollapsibleBadge {{
    background-color: {P['primary']};
    color: white;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: bold;
}}

#CollapsibleContent {{
    background-color: {P['surface']};
    border: 1px solid {P['border']};
    border-top: none;
    border-radius: 0 0 6px 6px;
}}

/* CollapsiblePanel quand replie - header avec border-radius complet */
CollapsiblePanel[collapsed="true"] #CollapsibleHeader {{
    border-radius: 6px;
}}
"""

    def ForceRefresh(self):
        """Force le rafraîchissement du thème"""
        self._ApplyCurrentTheme()

    def StopMonitoring(self):
        """Arrête le timer de monitoring"""
        if self.CheckTimer:
            self.CheckTimer.stop()
            self.Logger.info("Monitoring du thème arrêté")


def ApplyTheme(App: QApplication, UserPreference: str = None) -> ThemeManager:
    """
    Fonction utilitaire pour appliquer le thème à une application

    Args:
        App: Instance de QApplication
        UserPreference: Préférence utilisateur (optionnel)

    Returns:
        Instance du ThemeManager
    """
    Manager = ThemeManager(App)

    if UserPreference:
        Manager.SetUserPreference(UserPreference)

    return Manager
