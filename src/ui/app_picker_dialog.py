import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QLabel
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from utils.desktop_entry_scanner import get_installed_desktop_entries

class AppPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_app = None
        self.all_apps = []
        self.init_ui()
        self.load_applications()

    def init_ui(self):
        self.setWindowTitle("Add Applications to Protect")
        self.setFixedSize(450, 500)
        self.setModal(True)
        
        # Dark Premium QSS
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                border: 1px solid #3a3a4a;
                border-radius: 12px;
            }
            QLabel {
                color: #e2e8f0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #2d2d3a;
                border: 1px solid #4a4a5a;
                border-radius: 6px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 14px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
            }
            QListWidget {
                background-color: #18181c;
                border: 1px solid #2d2d3a;
                border-radius: 8px;
                color: #e2e8f0;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #2d2d3a;
                color: #ffffff;
            }
            QListWidget::item:selected {
                background-color: #4f46e5;
                color: #ffffff;
            }
            QPushButton {
                background-color: #4f46e5;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton:hover {
                background-color: #4338ca;
            }
            QPushButton:pressed {
                background-color: #3730a3;
            }
            QPushButton#cancelBtn {
                background-color: #374151;
                color: #d1d5db;
            }
            QPushButton#cancelBtn:hover {
                background-color: #4b5563;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Info
        header_label = QLabel("Select an installed application to protect:")
        header_label.setStyleSheet("font-weight: 500; font-size: 14px;")
        layout.addWidget(header_label)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search applications...")
        self.search_input.textChanged.connect(self.filter_applications)
        layout.addWidget(self.search_input)

        # List Widget
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(24, 24))
        self.list_widget.itemDoubleClicked.connect(self.accept_selection)
        layout.addWidget(self.list_widget)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.ok_btn = QPushButton("Add Protection")
        self.ok_btn.clicked.connect(self.accept_selection)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def load_applications(self):
        self.all_apps = get_installed_desktop_entries()
        self.populate_list(self.all_apps)

    def populate_list(self, apps_list):
        self.list_widget.clear()
        for app in apps_list:
            item = QListWidgetItem(app["name"])
            
            # Resolve QIcon from theme or path
            icon = None
            icon_source = app["icon"]
            if icon_source:
                if os.path.isabs(icon_source) and os.path.exists(icon_source):
                    icon = QIcon(icon_source)
                else:
                    # QIcon.fromTheme automatically fallback to null if not found
                    icon = QIcon.fromTheme(icon_source)
                    
            if not icon or icon.isNull():
                # Generic app icon fallback
                icon = QIcon.fromTheme("application-x-executable")
                
            item.setIcon(icon)
            item.setData(Qt.ItemDataRole.UserRole, app)
            self.list_widget.addItem(item)

    def filter_applications(self, text):
        query = text.lower()
        filtered = [app for app in self.all_apps if query in app["name"].lower() or query in app["executable"].lower()]
        self.populate_list(filtered)

    def accept_selection(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            self.selected_app = selected_items[0].data(Qt.ItemDataRole.UserRole)
            self.accept()
        else:
            self.reject()
