from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QLabel, QWidget
)
from PySide6.QtCore import Qt, QSize
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
        self.setFixedSize(450, 520)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        from ui.theme import get_theme_qss, get_colors, style_heading, CustomTitleBar, WindowDragResizeFilter
        c = get_colors()
        self.setStyleSheet(get_theme_qss())

        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)

        self.main_container = QWidget()
        self.main_container.setObjectName("mainContainer")
        self.main_container.setStyleSheet(f"""
            QWidget#mainContainer {{
                background-color: {c["BG_NEUTRAL"]};
                border: 1px solid {c["BORDER_NEUTRAL"]};
                border-radius: 14px;
            }}
        """)
        window_layout.addWidget(self.main_container)
        self.drag_filter = WindowDragResizeFilter(self)

        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self, title="Add Applications to Protect", allow_maximize=False, allow_minimize=False)
        container_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        container_layout.addWidget(content_widget)

        # Header Info
        header_label = QLabel("Select an installed application to protect:")
        style_heading(header_label, 14)
        layout.addWidget(header_label)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search applications...")
        self.search_input.textChanged.connect(self.filter_applications)
        self.search_input.returnPressed.connect(self.accept_selection)
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
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.accept_selection)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept_selection()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
        elif event.key() == Qt.Key.Key_Down and self.search_input.hasFocus():
            self.list_widget.setFocus()
            if self.list_widget.count() > 0 and self.list_widget.currentRow() < 0:
                self.list_widget.setCurrentRow(0)
            event.accept()
        else:
            super().keyPressEvent(event)

    def load_applications(self):
        self.all_apps = get_installed_desktop_entries()
        self.populate_list(self.all_apps)

    def populate_list(self, apps_list):
        self.list_widget.clear()
        from ui.theme import resolve_app_icon
        for app in apps_list:
            item = QListWidgetItem(app["name"])
            
            # Resolve QIcon using theme utility
            icon = resolve_app_icon(app.get("icon", ""))
                
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
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Selection", "Select an application first.")
