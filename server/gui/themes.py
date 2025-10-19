"""
Centralized theme and styling module for the GUI
Provides color palette, font definitions, and reusable stylesheet generators
"""

from typing import Optional


class Colors:
    """Color palette for dark theme"""

    # Background colors
    BACKGROUND_DARK = "#1e1e1e"
    BACKGROUND = "#2b2b2b"
    BACKGROUND_LIGHT = "#3c3c3c"

    # Text colors
    TEXT_PRIMARY = "#e0e0e0"
    TEXT_SECONDARY = "#888888"
    TEXT_WHITE = "#ffffff"

    # Primary accent colors
    PRIMARY = "#0d7377"
    PRIMARY_HOVER = "#14a085"
    PRIMARY_PRESSED = "#0a5a5d"

    # Status colors
    SUCCESS = "#4CAF50"
    SUCCESS_DARK = "#388E3C"
    ERROR = "#f44336"
    ERROR_DARK = "#d32f2f"
    WARNING = "#FF9800"
    INFO = "#2196F3"

    # Border colors
    BORDER = "#555555"
    BORDER_FOCUS = "#0d7377"

    # Special colors for table cells
    ONLINE_BG = "#0d7377"  # Same as PRIMARY for consistency
    OFFLINE_BG = "#f44336"  # Same as ERROR


class Fonts:
    """Font definitions"""

    DEFAULT_FAMILY = "Arial"
    MONO_FAMILY = "Consolas"

    # Font sizes
    SIZE_SMALL = 9
    SIZE_NORMAL = 10
    SIZE_MEDIUM = 11
    SIZE_LARGE = 12


def get_dark_theme_stylesheet() -> str:
    """
    Returns the complete dark theme stylesheet for the application

    Returns:
        str: Complete CSS stylesheet
    """
    return f"""
        QMainWindow, QWidget {{
            background-color: {Colors.BACKGROUND_DARK};
            color: {Colors.TEXT_PRIMARY};
        }}

        QGroupBox {{
            font-weight: bold;
            border: 2px solid {Colors.BORDER};
            border-radius: 5px;
            margin-top: 1ex;
            padding-top: 5px;
            background-color: {Colors.BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
            color: {Colors.TEXT_PRIMARY};
        }}

        QPushButton {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_WHITE};
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }}

        QPushButton:hover {{
            background-color: {Colors.PRIMARY_HOVER};
        }}

        QPushButton:pressed {{
            background-color: {Colors.PRIMARY_PRESSED};
        }}

        QPushButton:disabled {{
            background-color: {Colors.BACKGROUND_LIGHT};
            color: {Colors.TEXT_SECONDARY};
        }}

        QLabel {{
            color: {Colors.TEXT_PRIMARY};
            background-color: transparent;
        }}

        QLineEdit, QSpinBox, QComboBox {{
            background-color: {Colors.BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER};
            border-radius: 3px;
            padding: 5px;
        }}

        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 1px solid {Colors.BORDER_FOCUS};
        }}

        QComboBox::drop-down {{
            border: none;
            background-color: {Colors.BACKGROUND_LIGHT};
        }}

        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid {Colors.TEXT_PRIMARY};
            margin-right: 5px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {Colors.BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.PRIMARY};
            border: 1px solid {Colors.BORDER};
        }}

        QTableWidget {{
            background-color: {Colors.BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
            gridline-color: {Colors.BORDER};
            border: 1px solid {Colors.BORDER};
        }}

        QTableWidget::item {{
            padding: 5px;
        }}

        QTableWidget::item:selected {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_WHITE};
        }}

        QHeaderView::section {{
            background-color: {Colors.BACKGROUND_LIGHT};
            color: {Colors.TEXT_PRIMARY};
            padding: 5px;
            border: 1px solid {Colors.BORDER};
            font-weight: bold;
        }}

        QPlainTextEdit, QTextEdit {{
            background-color: {Colors.BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER};
            border-radius: 3px;
        }}

        QScrollBar:vertical {{
            background-color: {Colors.BACKGROUND};
            width: 12px;
            border: none;
        }}

        QScrollBar::handle:vertical {{
            background-color: {Colors.BORDER};
            border-radius: 6px;
            min-height: 20px;
        }}

        QScrollBar::handle:vertical:hover {{
            background-color: {Colors.PRIMARY};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        QScrollBar:horizontal {{
            background-color: {Colors.BACKGROUND};
            height: 12px;
            border: none;
        }}

        QScrollBar::handle:horizontal {{
            background-color: {Colors.BORDER};
            border-radius: 6px;
            min-width: 20px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background-color: {Colors.PRIMARY};
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        QCheckBox {{
            color: {Colors.TEXT_PRIMARY};
            spacing: 5px;
        }}

        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {Colors.BORDER};
            border-radius: 3px;
            background-color: {Colors.BACKGROUND};
        }}

        QCheckBox::indicator:checked {{
            background-color: {Colors.PRIMARY};
            border: 1px solid {Colors.PRIMARY};
        }}

        QCheckBox::indicator:hover {{
            border: 1px solid {Colors.PRIMARY_HOVER};
        }}

        QProgressBar {{
            background-color: {Colors.BACKGROUND};
            border: 1px solid {Colors.BORDER};
            border-radius: 3px;
            text-align: center;
            color: {Colors.TEXT_PRIMARY};
        }}

        QProgressBar::chunk {{
            background-color: {Colors.PRIMARY};
            border-radius: 2px;
        }}

        QTabWidget::pane {{
            border: 1px solid {Colors.BORDER};
            background-color: {Colors.BACKGROUND_DARK};
        }}

        QTabBar::tab {{
            background-color: {Colors.BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
            padding: 8px 16px;
            border: 1px solid {Colors.BORDER};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }}

        QTabBar::tab:selected {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_WHITE};
        }}

        QTabBar::tab:hover {{
            background-color: {Colors.BACKGROUND_LIGHT};
        }}

        QFrame {{
            background-color: {Colors.BACKGROUND};
            border: 1px solid {Colors.BORDER};
        }}

        QScrollArea {{
            background-color: {Colors.BACKGROUND_DARK};
            border: none;
        }}

        QMessageBox {{
            background-color: {Colors.BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
        }}

        QMessageBox QLabel {{
            color: {Colors.TEXT_PRIMARY};
        }}

        QMessageBox QPushButton {{
            min-width: 80px;
        }}

        QStatusBar {{
            background-color: {Colors.BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
            border-top: 1px solid {Colors.BORDER};
        }}
    """


def get_button_style(variant: str = "primary") -> str:
    """
    Returns button stylesheet for different variants

    Args:
        variant: Button variant - "primary", "success", "danger", "warning"

    Returns:
        str: Button CSS stylesheet
    """
    styles = {
        "primary": f"""
            QPushButton {{
                background-color: {Colors.PRIMARY};
                color: {Colors.TEXT_WHITE};
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background-color: {Colors.PRIMARY_HOVER};
            }}
        """,
        "success": f"""
            QPushButton {{
                background-color: {Colors.SUCCESS};
                color: {Colors.TEXT_WHITE};
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SUCCESS_DARK};
            }}
        """,
        "danger": f"""
            QPushButton {{
                background-color: {Colors.ERROR};
                color: {Colors.TEXT_WHITE};
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ERROR_DARK};
            }}
        """,
        "warning": f"""
            QPushButton {{
                background-color: {Colors.WARNING};
                color: {Colors.TEXT_WHITE};
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background-color: #F57C00;
            }}
        """
    }

    return styles.get(variant, styles["primary"])


def get_status_label_style(status: str) -> str:
    """
    Returns label stylesheet for status indicators

    Args:
        status: Status type - "online", "offline", "success", "error", "warning", "info"

    Returns:
        str: Label CSS stylesheet with appropriate color
    """
    styles = {
        "online": f"color: {Colors.SUCCESS}; font-weight: bold;",
        "offline": f"color: {Colors.ERROR}; font-weight: bold;",
        "success": f"color: {Colors.SUCCESS}; font-weight: bold;",
        "error": f"color: {Colors.ERROR}; font-weight: bold;",
        "warning": f"color: {Colors.WARNING};",
        "info": f"color: {Colors.INFO};",
        "processing": f"color: {Colors.INFO};",
        "pending": f"color: {Colors.WARNING};",
        "completed": f"color: {Colors.SUCCESS};",
    }

    return styles.get(status, f"color: {Colors.TEXT_PRIMARY};")


def get_batch_status_widget_style() -> str:
    """
    Returns stylesheet for batch status widgets

    Returns:
        str: CSS stylesheet for BatchStatusWidget
    """
    return f"""
        BatchStatusWidget {{
            border: 1px solid {Colors.BORDER};
            border-radius: 5px;
            background-color: {Colors.BACKGROUND};
            margin: 2px;
        }}
    """


def get_table_cell_colors(status: str) -> tuple:
    """
    Returns background and foreground colors for table cells

    Args:
        status: Status type - "online", "offline"

    Returns:
        tuple: (background_color, foreground_color) as RGB tuples
    """
    if status == "online":
        return (13, 115, 119), (255, 255, 255)  # PRIMARY, WHITE
    elif status == "offline":
        return (244, 67, 54), (255, 255, 255)  # ERROR, WHITE
    else:
        return (43, 43, 43), (224, 224, 224)  # BACKGROUND, TEXT_PRIMARY


def get_font(family: str = "default", size: Optional[int] = None) -> tuple:
    """
    Returns font family and size

    Args:
        family: Font family - "default", "mono"
        size: Font size (uses default if None)

    Returns:
        tuple: (font_family, font_size)
    """
    font_family = Fonts.MONO_FAMILY if family == "mono" else Fonts.DEFAULT_FAMILY
    font_size = size if size is not None else Fonts.SIZE_NORMAL

    return font_family, font_size
