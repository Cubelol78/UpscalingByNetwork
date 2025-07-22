import sys
import os
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QTabWidget, QLabel, QPushButton, QTableWidget, 
                            QTableWidgetItem, QProgressBar, QTextEdit, QGroupBox,
                            QGridLayout, QFileDialog, QMessageBox, QSplitter,
                            QFrame, QScrollArea, QComboBox, QSpinBox, QCheckBox,
                            QSlider, QApplication, QHeaderView)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QPixmap, QIcon, QPalette, QColor
import pyqtgraph as pg
from datetime import datetime
import json

from config.settings import config
from utils.logger import get_logger
from utils.file_utils import format_file_size, format_duration
from utils.performance_monitor import performance_monitor
