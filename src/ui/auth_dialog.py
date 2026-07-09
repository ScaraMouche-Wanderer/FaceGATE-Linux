import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)
from PySide6.QtCore import Qt, QTimer
from security.placeholder_auth import verify_password

class AuthDialog(QDialog):
    def __init__(self, app_name: str, timeout_seconds: int = 0, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.timeout_seconds = timeout_seconds
        self.authenticated = False
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("FaceGate Authentication")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Dialog | 
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.CustomizeWindowHint
        )
        self.setModal(True)
        self.setFixedSize(380, 220)
        
        # Modern Premium Dark Styling
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                border: 1px solid #3a3a4a;
                border-radius: 12px;
            }
            QLabel {
                color: #e2e8f0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLineEdit {
                background-color: #2d2d3a;
                border: 1px solid #4a4a5a;
                border-radius: 6px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
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
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header Info
        header_label = QLabel(f"🔒 <b>{self.app_name}</b> is locked.")
        header_label.setStyleSheet("font-size: 16px; font-weight: 500;")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        sub_label = QLabel("Enter password to unlock application:")
        sub_label.setStyleSheet("font-size: 13px; color: #a0aec0;")
        sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub_label)

        # Password Input
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Password")
        self.password_input.returnPressed.connect(self.handle_unlock)
        layout.addWidget(self.password_input)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: bold;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.unlock_btn = QPushButton("Unlock")
        self.unlock_btn.clicked.connect(self.handle_unlock)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.unlock_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)
        
        # Set focus to password field after dialog renders
        QTimer.singleShot(50, self.password_input.setFocus)
        
        # Setup timeout timer if specified
        if self.timeout_seconds > 0:
            self.timeout_timer = QTimer(self)
            self.timeout_timer.setSingleShot(True)
            self.timeout_timer.timeout.connect(self.handle_timeout)
            self.timeout_timer.start(self.timeout_seconds * 1000)

    def handle_timeout(self):
        logging.warning(f"Authentication dialog for '{self.app_name}' timed out after {self.timeout_seconds}s.")
        self.reject()

    def handle_unlock(self):
        password = self.password_input.text()
        if verify_password(password):
            self.authenticated = True
            self.accept()
        else:
            self.error_label.setText("⚠️ Incorrect password. Try again.")
            self.password_input.selectAll()
            
            # Temporary error styling
            self.password_input.setStyleSheet("""
                QLineEdit {
                    background-color: #2d2d3a;
                    border: 1px solid #ef4444;
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: #ffffff;
                    font-size: 14px;
                }
            """)
            # Revert to standard styling on edit or after 1.5 seconds
            QTimer.singleShot(1500, self.reset_input_style)

    def reset_input_style(self):
        self.password_input.setStyleSheet("")
