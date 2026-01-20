"""
Widget de panneau depliable avec en-tete cliquable
Supporte titre, badge optionnel et animation
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont


class CollapsiblePanel(QWidget):
    """Panneau depliable avec en-tete cliquable"""

    # Signal emis quand l'etat change (True = deplie)
    Toggled = pyqtSignal(bool)

    def __init__(self, Title: str, Expanded: bool = True, Parent=None):
        """
        Initialise le panneau depliable

        Args:
            Title: Titre du panneau
            Expanded: Etat initial (True = deplie)
            Parent: Widget parent
        """
        super().__init__(Parent)
        self._Expanded = Expanded
        self._Title = Title
        self._Badge = ""
        self._AnimationDuration = 150

        self.SetupUI()
        self.SetExpanded(Expanded, Animate=False)

    def SetupUI(self):
        """Configure l'interface"""
        MainLayout = QVBoxLayout(self)
        MainLayout.setContentsMargins(0, 0, 0, 0)
        MainLayout.setSpacing(0)

        # En-tete cliquable
        self.HeaderFrame = QFrame()
        self.HeaderFrame.setObjectName("CollapsibleHeader")
        self.HeaderFrame.setCursor(Qt.PointingHandCursor)
        self.HeaderFrame.mousePressEvent = self._OnHeaderClicked

        HeaderLayout = QHBoxLayout(self.HeaderFrame)
        HeaderLayout.setContentsMargins(12, 8, 12, 8)

        # Fleche indicatrice
        self.ArrowLabel = QLabel()
        self.ArrowLabel.setObjectName("CollapsibleArrow")
        self.ArrowLabel.setFixedWidth(20)
        HeaderLayout.addWidget(self.ArrowLabel)

        # Titre
        self.TitleLabel = QLabel(self._Title)
        self.TitleLabel.setObjectName("CollapsibleTitle")
        TitleFont = QFont()
        TitleFont.setBold(True)
        self.TitleLabel.setFont(TitleFont)
        HeaderLayout.addWidget(self.TitleLabel)

        HeaderLayout.addStretch()

        # Badge optionnel
        self.BadgeLabel = QLabel()
        self.BadgeLabel.setObjectName("CollapsibleBadge")
        self.BadgeLabel.setVisible(False)
        HeaderLayout.addWidget(self.BadgeLabel)

        MainLayout.addWidget(self.HeaderFrame)

        # Conteneur pour le contenu
        self.ContentContainer = QFrame()
        self.ContentContainer.setObjectName("CollapsibleContent")
        self.ContentLayout = QVBoxLayout(self.ContentContainer)
        self.ContentLayout.setContentsMargins(12, 8, 12, 12)
        self.ContentLayout.setSpacing(8)

        MainLayout.addWidget(self.ContentContainer)

        # Animation pour le conteneur
        self.Animation = QPropertyAnimation(self.ContentContainer, b"maximumHeight")
        self.Animation.setDuration(self._AnimationDuration)
        self.Animation.setEasingCurve(QEasingCurve.OutCubic)

    def _OnHeaderClicked(self, Event):
        """Gere le clic sur l'en-tete"""
        self.Toggle()

    def Toggle(self):
        """Bascule l'etat du panneau"""
        self.SetExpanded(not self._Expanded)

    def SetExpanded(self, Expanded: bool, Animate: bool = True):
        """
        Definit l'etat du panneau

        Args:
            Expanded: True pour deplier, False pour replier
            Animate: True pour animer la transition
        """
        if self._Expanded == Expanded and self.ContentContainer.isVisible() == Expanded:
            return

        self._Expanded = Expanded

        # Met a jour la fleche
        self._UpdateArrow()

        if Animate:
            # Animation
            self.Animation.stop()
            if Expanded:
                self.ContentContainer.setVisible(True)
                self.ContentContainer.setMaximumHeight(0)
                self.Animation.setStartValue(0)
                self.Animation.setEndValue(self.ContentContainer.sizeHint().height() + 100)
                self.Animation.finished.connect(self._OnExpandFinished)
            else:
                self.Animation.setStartValue(self.ContentContainer.height())
                self.Animation.setEndValue(0)
                self.Animation.finished.connect(self._OnCollapseFinished)
            self.Animation.start()
        else:
            # Changement immediat
            self.ContentContainer.setVisible(Expanded)
            if Expanded:
                self.ContentContainer.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            else:
                self.ContentContainer.setMaximumHeight(0)

        self.Toggled.emit(Expanded)

    def _OnExpandFinished(self):
        """Appele quand l'animation d'expansion est terminee"""
        self.Animation.finished.disconnect(self._OnExpandFinished)
        self.ContentContainer.setMaximumHeight(16777215)

    def _OnCollapseFinished(self):
        """Appele quand l'animation de repli est terminee"""
        self.Animation.finished.disconnect(self._OnCollapseFinished)
        self.ContentContainer.setVisible(False)

    def _UpdateArrow(self):
        """Met a jour le symbole de la fleche"""
        if self._Expanded:
            self.ArrowLabel.setText("\u25BC")  # Triangle vers le bas
        else:
            self.ArrowLabel.setText("\u25B6")  # Triangle vers la droite

    def IsExpanded(self) -> bool:
        """Retourne l'etat du panneau"""
        return self._Expanded

    def SetTitle(self, Title: str):
        """Definit le titre du panneau"""
        self._Title = Title
        self.TitleLabel.setText(Title)

    def GetTitle(self) -> str:
        """Retourne le titre du panneau"""
        return self._Title

    def SetBadge(self, Text: str):
        """
        Definit le badge du panneau

        Args:
            Text: Texte du badge (ex: "3 GPUs", "OK")
        """
        self._Badge = Text
        self.BadgeLabel.setText(Text)
        self.BadgeLabel.setVisible(bool(Text))

    def GetBadge(self) -> str:
        """Retourne le texte du badge"""
        return self._Badge

    def AddWidget(self, Widget: QWidget):
        """
        Ajoute un widget au contenu du panneau

        Args:
            Widget: Widget a ajouter
        """
        self.ContentLayout.addWidget(Widget)

    def AddLayout(self, Layout):
        """
        Ajoute un layout au contenu du panneau

        Args:
            Layout: Layout a ajouter
        """
        self.ContentLayout.addLayout(Layout)

    def GetContentLayout(self) -> QVBoxLayout:
        """Retourne le layout du contenu"""
        return self.ContentLayout

    def SetAnimationDuration(self, Ms: int):
        """Definit la duree de l'animation en millisecondes"""
        self._AnimationDuration = Ms
        self.Animation.setDuration(Ms)

    def Clear(self):
        """Supprime tout le contenu du panneau"""
        while self.ContentLayout.count():
            Item = self.ContentLayout.takeAt(0)
            if Item.widget():
                Item.widget().deleteLater()
            elif Item.layout():
                self._ClearLayout(Item.layout())

    def _ClearLayout(self, Layout):
        """Supprime recursivement le contenu d'un layout"""
        while Layout.count():
            Item = Layout.takeAt(0)
            if Item.widget():
                Item.widget().deleteLater()
            elif Item.layout():
                self._ClearLayout(Item.layout())
