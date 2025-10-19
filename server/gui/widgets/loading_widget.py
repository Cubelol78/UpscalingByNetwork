"""
Widgets de chargement pour afficher l'état des opérations longues
"""

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QRect, pyqtProperty
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
import math


class LoadingSpinner(QWidget):
    """Widget de spinner rotatif pour indiquer une opération en cours"""

    def __init__(self, size=32, color=None, parent=None):
        super().__init__(parent)
        self.size = size
        self.color = color or QColor(13, 115, 119)  # Couleur par défaut (thème)
        self.angle = 0

        self.setFixedSize(size, size)

        # Timer pour l'animation
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)

    def start(self):
        """Démarre l'animation du spinner"""
        self.timer.start(50)  # 50ms = 20 FPS

    def stop(self):
        """Arrête l'animation du spinner"""
        self.timer.stop()
        self.angle = 0
        self.update()

    def rotate(self):
        """Rotation du spinner"""
        self.angle = (self.angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        """Dessine le spinner"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Centre du widget
        center_x = self.width() / 2
        center_y = self.height() / 2
        radius = (self.size / 2) - 4

        # Dessiner 8 lignes avec opacité décroissante
        for i in range(8):
            angle = math.radians(self.angle + i * 45)

            # Opacité décroissante pour créer l'effet de rotation
            opacity = 255 - (i * 25)

            # Calculer les positions de début et fin de ligne
            start_x = center_x + (radius * 0.5) * math.cos(angle)
            start_y = center_y + (radius * 0.5) * math.sin(angle)
            end_x = center_x + radius * math.cos(angle)
            end_y = center_y + radius * math.sin(angle)

            # Configurer le stylo avec la couleur et l'opacité
            color = QColor(self.color)
            color.setAlpha(opacity)
            pen = QPen(color)
            pen.setWidth(3)
            pen.setCapStyle(Qt.RoundCap)

            painter.setPen(pen)
            painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))


class LoadingOverlay(QWidget):
    """Overlay semi-transparent avec spinner et message pour les opérations longues"""

    def __init__(self, message="Chargement...", parent=None):
        super().__init__(parent)
        self.message = message

        # Configuration de l'overlay
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # Layout principal
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Container pour le contenu (avec fond)
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 230);
                border: 2px solid #0d7377;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(15)
        container_layout.setAlignment(Qt.AlignCenter)

        # Spinner
        self.spinner = LoadingSpinner(size=48, parent=self)
        container_layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        # Label du message
        self.message_label = QLabel(message)
        self.message_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
                border: none;
            }
        """)
        self.message_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self.message_label)

        # Label secondaire (optionnel, pour des détails supplémentaires)
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("""
            QLabel {
                color: #b0b0b0;
                font-size: 11px;
                background: transparent;
                border: none;
            }
        """)
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.hide()
        container_layout.addWidget(self.detail_label)

        layout.addWidget(container)

        # Masquer par défaut
        self.hide()

    def showEvent(self, event):
        """Démarre le spinner quand l'overlay est affiché"""
        super().showEvent(event)
        self.spinner.start()

        # S'assurer que l'overlay couvre tout le parent
        if self.parent():
            self.setGeometry(self.parent().rect())

    def hideEvent(self, event):
        """Arrête le spinner quand l'overlay est masqué"""
        super().hideEvent(event)
        self.spinner.stop()

    def resizeEvent(self, event):
        """Ajuste la taille de l'overlay quand le parent est redimensionné"""
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())

    def set_message(self, message: str):
        """Met à jour le message principal"""
        self.message = message
        self.message_label.setText(message)

    def set_detail(self, detail: str):
        """Met à jour le message de détail (optionnel)"""
        if detail:
            self.detail_label.setText(detail)
            self.detail_label.show()
        else:
            self.detail_label.hide()

    def paintEvent(self, event):
        """Dessine le fond semi-transparent"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))


class InlineLoadingIndicator(QWidget):
    """Indicateur de chargement inline pour les boutons et barres d'état"""

    def __init__(self, message="", size=16, parent=None):
        super().__init__(parent)

        # Layout horizontal
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Mini spinner
        self.spinner = LoadingSpinner(size=size, parent=self)
        layout.addWidget(self.spinner)

        # Message
        self.message_label = QLabel(message)
        self.message_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 11px;
                background: transparent;
            }
        """)
        layout.addWidget(self.message_label)

        layout.addStretch()

    def start(self, message=""):
        """Démarre l'indicateur avec un message optionnel"""
        if message:
            self.message_label.setText(message)
        self.spinner.start()
        self.show()

    def stop(self):
        """Arrête l'indicateur"""
        self.spinner.stop()
        self.hide()

    def set_message(self, message: str):
        """Met à jour le message"""
        self.message_label.setText(message)
