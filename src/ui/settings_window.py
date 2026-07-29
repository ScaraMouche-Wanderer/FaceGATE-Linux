import os
import ctypes

# Preload libc and librt with RTLD_GLOBAL to resolve GLIBC symbol conflicts (__pointer_chk_guard) on Linux
try:
    ctypes.CDLL("libc.so.6", mode=ctypes.RTLD_GLOBAL)
except Exception:
    pass
try:
    ctypes.CDLL("librt.so.1", mode=ctypes.RTLD_GLOBAL)
except Exception:
    pass

import subprocess
import logging
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QStackedWidget,
    QWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QCheckBox, QMessageBox, QLineEdit, QTreeWidget, QTreeWidgetItem, QListView
)
from PySide6.QtCore import Qt, QSize, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon
from utils.config_loader import get_config
from utils.systemd_manager import is_enabled, enable, disable
from ui.app_picker_dialog import AppPickerDialog
from locking.launcher_sub import apply_substitution, restore_substitution
from ui.theme import AnimatedComboBox, AnimatedCheckBox, AnimatedSpinBox

class AnimatedSidebar(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(190)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.anim = None
        self.max_anim = None
        self.setMouseTracking(True)
        
    def enterEvent(self, event):
        if self.anim:
            self.anim.stop()
        if self.max_anim:
            self.max_anim.stop()
            
        self.anim = QPropertyAnimation(self, b"minimumWidth")
        self.anim.setDuration(220)
        self.anim.setStartValue(self.width())
        self.anim.setEndValue(215)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        self.max_anim = QPropertyAnimation(self, b"maximumWidth")
        self.max_anim.setDuration(220)
        self.max_anim.setStartValue(self.width())
        self.max_anim.setEndValue(215)
        self.max_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        self.anim.start()
        self.max_anim.start()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        if self.anim:
            self.anim.stop()
        if self.max_anim:
            self.max_anim.stop()
            
        self.anim = QPropertyAnimation(self, b"minimumWidth")
        self.anim.setDuration(220)
        self.anim.setStartValue(self.width())
        self.anim.setEndValue(190)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        self.max_anim = QPropertyAnimation(self, b"maximumWidth")
        self.max_anim.setDuration(220)
        self.max_anim.setStartValue(self.width())
        self.max_anim.setEndValue(190)
        self.max_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        self.anim.start()
        self.max_anim.start()
        super().leaveEvent(event)


class ChangePasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Change Master Password")
        self.setModal(True)
        self.resize(460, 480)
        self.setMinimumSize(440, 460)

        from utils.config_loader import get_config
        from ui.theme import is_system_dark_mode, get_colors, get_theme_qss, CustomTitleBar, style_heading
        
        _cfg_theme = get_config().get("behavior.theme", "system")
        if _cfg_theme == "system":
            self.theme_mode = "dark" if is_system_dark_mode() else "light"
        else:
            self.theme_mode = _cfg_theme

        c = get_colors(self.theme_mode)
        self.setStyleSheet(get_theme_qss(self.theme_mode))
        self.setWindowFlags(Qt.WindowType.Dialog)

        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)

        self.main_container = QWidget()
        self.main_container.setObjectName("mainContainer")
        self.main_container.setStyleSheet(f"""
            QWidget#mainContainer {{
                background-color: {c["BG_NEUTRAL"]};
                border: 1px solid {c["BORDER_NEUTRAL"]};
                border-radius: 12px;
            }}
        """)
        window_layout.addWidget(self.main_container)

        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self, title="Change Master Password", allow_maximize=False, allow_minimize=False)
        container_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)
        container_layout.addWidget(content_widget)

        # Header Info
        header_label = QLabel("🔑 Change Master Password")
        style_heading(header_label, 18)
        header_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {c['TEXT_PRIMARY']}; border: none;")
        layout.addWidget(header_label)

        sub_desc = QLabel("Update your master encryption key. All face embeddings will be re-encrypted under the new credential.")
        sub_desc.setStyleSheet(f"font-size: 12px; color: {c['TEXT_SECONDARY']}; border: none;")
        sub_desc.setWordWrap(True)
        layout.addWidget(sub_desc)

        # Form fields
        from database.embedding_store import read_envelope_file
        envelope = read_envelope_file()
        self.has_current = envelope is not None

        input_css = f"""
            QLineEdit {{
                background-color: {c["WIDGET_BG"]};
                border: 1px solid {c["BORDER_NEUTRAL"]};
                border-radius: 6px;
                padding: 8px 12px;
                color: {c["TEXT_PRIMARY"]};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {c["ACCENT_PURPLE"]};
            }}
        """

        if self.has_current:
            self.current_label = QLabel("Current Master Password:")
            self.current_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {c['TEXT_PRIMARY']}; border: none;")
            self.current_input = QLineEdit()
            self.current_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.current_input.setPlaceholderText("Enter current master password")
            self.current_input.setStyleSheet(input_css)
            self.current_input.setMinimumHeight(40)
            layout.addWidget(self.current_label)
            layout.addWidget(self.current_input)
        else:
            self.current_input = None

        self.new_label = QLabel("New Master Password (min 8 chars):")
        self.new_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {c['TEXT_PRIMARY']}; border: none;")
        self.new_input = QLineEdit()
        self.new_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_input.setPlaceholderText("Enter new master password")
        self.new_input.setStyleSheet(input_css)
        self.new_input.setMinimumHeight(40)
        layout.addWidget(self.new_label)
        layout.addWidget(self.new_input)

        self.confirm_label = QLabel("Confirm New Password:")
        self.confirm_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {c['TEXT_PRIMARY']}; border: none;")
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input.setPlaceholderText("Re-type new master password")
        self.confirm_input.setStyleSheet(input_css)
        self.confirm_input.setMinimumHeight(40)
        layout.addWidget(self.confirm_label)
        layout.addWidget(self.confirm_input)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: bold; border: none;")
        layout.addWidget(self.error_label)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setMinimumHeight(38)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c["CANCEL_BTN_BG"]};
                color: {c["TEXT_PRIMARY"]};
                border: 1px solid {c["BORDER_NEUTRAL"]};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {c["CANCEL_BTN_HOVER"]};
            }}
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.ok_btn = QPushButton("Update Password")
        self.ok_btn.setMinimumHeight(38)
        self.ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c["ACCENT_PURPLE"]};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {c["ACCENT_PURPLE_HOVER"]};
            }}
        """)
        self.ok_btn.clicked.connect(self.handle_change)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

    def handle_change(self):
        current_pwd = self.current_input.text() if self.has_current else None
        new_pwd = self.new_input.text()
        confirm_pwd = self.confirm_input.text()

        if self.has_current and not current_pwd:
            self.error_label.setText("Please enter your current password.")
            return

        if len(new_pwd) < 8:
            self.error_label.setText("New password must be at least 8 characters.")
            return

        if new_pwd != confirm_pwd:
            self.error_label.setText("New passwords do not match.")
            return

        from security.credential_store import update_master_password
        try:
            update_master_password(current_pwd, new_pwd)
            self.accept()
        except ValueError as e:
            self.error_label.setText(str(e))
        except Exception as e:
            self.error_label.setText(f"Failed to update password: {e}")


class FaceVerificationTestDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FaceGATE Biometric Test & Verification")
        self.setModal(True)
        self.resize(480, 480)
        self.setMinimumSize(420, 440)
        
        self.detector = None
        self.camera_worker = None
        self.detector_worker = None
        self.enrolled_embeddings = {}
        self.admin_user = None
        
        from utils.config_loader import get_config
        from ui.theme import is_system_dark_mode, get_colors, get_theme_qss, CustomTitleBar
        _cfg_theme = get_config().get("behavior.theme", "system")
        if _cfg_theme == "system":
            self.theme_mode = "dark" if is_system_dark_mode() else "light"
        else:
            self.theme_mode = _cfg_theme
            
        c = get_colors(self.theme_mode)
        self.setStyleSheet(get_theme_qss(self.theme_mode))
        self.setWindowFlags(Qt.WindowType.Dialog)
        
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        
        self.main_container = QWidget()
        self.main_container.setObjectName("mainContainer")
        self.main_container.setStyleSheet(f"""
            QWidget#mainContainer {{
                background-color: {c["BG_NEUTRAL"]};
                border: 1px solid {c["BORDER_NEUTRAL"]};
                border-radius: 12px;
            }}
        """)
        window_layout.addWidget(self.main_container)
        
        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        self.title_bar = CustomTitleBar(self, title="Biometric Test & Verification", allow_maximize=False, allow_minimize=False)
        container_layout.addWidget(self.title_bar)
        
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        container_layout.addWidget(content_widget)
        
        header = QLabel("🔍 Real-time Biometric Matcher Test")
        header.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {c['TEXT_PRIMARY']};")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        self.status_label = QLabel("Initializing face recognition models...")
        self.status_label.setStyleSheet(f"font-size: 13px; color: {c['TEXT_SECONDARY']};")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.camera_label = QLabel()
        self.camera_label.setFixedSize(360, 270)
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setStyleSheet("border: 2px solid #3a3a4a; border-radius: 8px; background-color: #0d0d11;")
        layout.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.match_card = QWidget()
        self.match_card.setStyleSheet(f"background-color: {c.get('BG_SECONDARY', c.get('WIDGET_BG', '#1f1d29'))}; border: 1px solid {c.get('BORDER_NEUTRAL', '#2c2a38')}; border-radius: 8px; padding: 6px;")
        m_layout = QVBoxLayout(self.match_card)
        m_layout.setContentsMargins(10, 6, 10, 6)
        
        self.match_info_label = QLabel("Position your face in view to test live recognition...")
        self.match_info_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {c['TEXT_PRIMARY']};")
        self.match_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        m_layout.addWidget(self.match_info_label)
        layout.addWidget(self.match_card)
        
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close Test")
        close_btn.setObjectName("cancelBtn")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self.start_camera_and_models)

    def start_camera_and_models(self):
        from ui.auth_dialog import DetectorLoader
        self.loader = DetectorLoader(self)
        self.loader.loaded.connect(self.on_detector_loaded)
        self.loader.error.connect(self.on_detector_load_error)
        self.loader.start()

    def on_detector_loaded(self, detector):
        try:
            self.detector = detector
            from database.embedding_store import load_embeddings, get_admin_user
            self.enrolled_embeddings = load_embeddings()
            self.admin_user = get_admin_user()
            
            from ui.auth_dialog import FaceDetectorWorker
            self.detector_worker = FaceDetectorWorker(self.detector)
            self.detector_worker.detected.connect(self.handle_detection_result)
            self.detector_worker.start()
            
            from camera.camera_worker import CameraWorker
            self.camera_worker = CameraWorker()
            self.camera_worker.signals.frame_ready.connect(self.handle_frame, Qt.ConnectionType.QueuedConnection)
            self.camera_worker.signals.error.connect(self.handle_camera_error, Qt.ConnectionType.QueuedConnection)
            self.status_label.setText("Camera active — Live verification running.")
            self.camera_worker.start()
        except Exception as e:
            self.status_label.setText(f"Error starting test: {e}")

    def on_detector_load_error(self, err_msg):
        self.status_label.setText(f"Model error: {err_msg}")

    def handle_camera_error(self, err_msg):
        self.status_label.setText(f"Camera error: {err_msg}")

    def handle_frame(self, frame):
        if hasattr(self, "detector_worker") and self.detector_worker:
            self.detector_worker.submit_frame(frame)

    def handle_detection_result(self, faces, frame):
        import cv2
        from ui.auth_dialog import convert_cv_to_pixmap
        from recognition.matcher import match_face
        from ui.theme import get_colors
        c = get_colors(self.theme_mode)
        
        display_frame = frame.copy()
        matched_user = None
        matched_score = 0.0
        
        if not faces:
            self.match_info_label.setText("👤 No face detected. Look directly at camera.")
            self.match_info_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {c['TEXT_SECONDARY']};")
        else:
            for face in faces:
                bbox = face['bbox']
                emb = face['embedding']
                name, score = match_face(emb, self.enrolled_embeddings)
                
                if name:
                    matched_user = name
                    matched_score = score
                    color = (0, 255, 0)
                    label_text = f"{name} ({score:.2f})"
                else:
                    color = (0, 0, 255)
                    label_text = "Unknown"
                    
                cv2.rectangle(display_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
                cv2.putText(display_frame, label_text, (bbox[0], bbox[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
            if matched_user:
                is_admin = (matched_user == self.admin_user)
                role_title = "👑 Primary Admin" if is_admin else "👤 Enrolled Profile"
                self.match_info_label.setText(f"✅ VERIFIED: {matched_user} | Score: {matched_score:.2f} | {role_title}")
                self.match_info_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #10b981;")
            else:
                self.match_info_label.setText("⚠️ Face Detected but Unrecognized / Low Similarity")
                self.match_info_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ef4444;")

        pixmap = convert_cv_to_pixmap(display_frame, 360, 270)
        self.camera_label.setPixmap(pixmap)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def reject(self):
        self.cleanup()
        super().reject()

    def accept(self):
        self.cleanup()
        super().accept()

    def cleanup(self):
        if hasattr(self, "camera_worker") and self.camera_worker:
            try:
                self.camera_worker.stop()
            except Exception:
                pass
            self.camera_worker = None
        if hasattr(self, "detector_worker") and self.detector_worker:
            try:
                self.detector_worker.stop()
            except Exception:
                pass
            self.detector_worker = None


class SettingsWindow(QDialog):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config if config else get_config()
        self._themed_labels = []  # List of (QLabel, str) to track and update theme colors dynamically
        self._scroll_areas = []   # QScrollArea references for scrollbar re-theming
        self._signals_connected = False  # Guard to prevent duplicate signal connections
        self._has_pending_changes = False  # Track whether user made changes requiring save auth
        self._loading = False  # Guard to suppress restart banner during load_settings
        
        # Keep track of initial apps list to perform delta substitutions on Save
        self.initial_apps = list(self.config.get("protected_apps", []))
        self.current_apps = list(self.initial_apps)
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle("FaceGate Settings")
        # Sizing based on content & screen resolution
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_size = screen.size()
            width = int(screen_size.width() * 0.5)
            height = int(screen_size.height() * 0.6)
            width = max(800, min(width, 1200))
            height = max(560, min(height, 800))
            self.resize(width + 20, height + 20)
            self.setMinimumSize(780 + 20, 520 + 20)
        else:
            self.resize(840, 580)
            self.setMinimumSize(800, 540)
            
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        
        from ui.theme import get_theme_qss, get_sidebar_qss, get_colors, CustomTitleBar
        c = get_colors()
        # Set base theme styling
        self.setStyleSheet(get_theme_qss() + get_sidebar_qss(c))

        # Outer layout
        self.window_layout = QVBoxLayout(self)
        self.window_layout.setContentsMargins(0, 0, 0, 0)
        
        # Main container with rounded corners and border
        self.main_container = QWidget()
        self.main_container.setObjectName("mainContainer")
        self.main_container.setStyleSheet(f"""
            QWidget#mainContainer {{
                background-color: {c["BG_NEUTRAL"]};
                border: 1px solid {c["BORDER_NEUTRAL"]};
                border-radius: 12px;
            }}
        """)
        
        # Shadow disabled (server-side decorations handle shadows now)
        self.shadow = None
        
        self.window_layout.addWidget(self.main_container)
        
        # Inner layout
        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Custom Title Bar
        self.title_bar = CustomTitleBar(self, title="FaceGate Settings", allow_maximize=True, allow_minimize=True)
        container_layout.addWidget(self.title_bar)
        
        # Horizontal content layout
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        container_layout.addLayout(main_layout)

        # 1. Left Sidebar Navigation
        self.sidebar = AnimatedSidebar(self)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setIconSize(QSize(18, 18))
        
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("system-lock-screen"), "Locked Apps"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("dialog-password"), "Authentication"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("preferences-system"), "Behavior"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("camera-web"), "Intruder Alerts"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("document-properties"), "Audit Logs"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("help-about"), "About"))
        
        self.sidebar.currentRowChanged.connect(self.switch_tab)
        main_layout.addWidget(self.sidebar)

        # 2. Right Stacked Widget Details area
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(24, 24, 24, 20)
        right_layout.setSpacing(16)

        self.tab_stack = QStackedWidget()
        
        # Create tabs
        self.create_locked_apps_tab()
        self.create_authentication_tab()
        self.create_behavior_tab()
        self.create_intruder_gallery_tab()
        self.create_logs_tab()
        self.create_about_tab()

        # Banner for daemon restart warning (initially hidden)
        from PySide6.QtWidgets import QFrame
        from ui.theme import get_colors as _gc
        _c = _gc()
        _banner_bg = "#2d261e" if _c.get("IS_DARK") else "#fffbeb"
        _banner_border = "#d97706"
        _banner_text = "#fef3c7" if _c.get("IS_DARK") else "#92400e"
        self.restart_banner = QFrame()
        self.restart_banner.setObjectName("restartBanner")
        self.restart_banner.setStyleSheet(f"""
            QFrame#restartBanner {{
                background-color: {_banner_bg};
                border: 1px solid {_banner_border};
                border-radius: 6px;
            }}
            QLabel {{
                color: {_banner_text};
                font-size: 13px;
                border: none;
            }}
            QPushButton {{
                background-color: #d97706;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #b45309;
            }}
        """)
        banner_layout = QHBoxLayout(self.restart_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        banner_layout.setSpacing(12)
        
        self.banner_label = QLabel("Some changes require restarting FaceGate to take effect.")
        self.restart_btn = QPushButton("Restart Now")
        self.restart_btn.clicked.connect(self.restart_daemon)
        self.dismiss_btn = QPushButton("Dismiss")
        self.dismiss_btn.setStyleSheet("background-color: transparent; color: #a1a1aa; text-decoration: underline; border: none;")
        self.dismiss_btn.clicked.connect(self.restart_banner.hide)
        
        banner_layout.addWidget(self.banner_label)
        banner_layout.addStretch()
        banner_layout.addWidget(self.restart_btn)
        banner_layout.addWidget(self.dismiss_btn)
        
        right_layout.addWidget(self.tab_stack)
        right_layout.addWidget(self.restart_banner)
        self.restart_banner.hide()

        # Footer Actions (Save / Cancel)
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save_and_close)
        
        footer_layout.addWidget(self.cancel_btn)
        footer_layout.addWidget(self.save_btn)
        right_layout.addLayout(footer_layout)

        main_layout.addWidget(right_container)
        self.sidebar.setCurrentRow(0)

    def wrap_in_scroll_area(self, widget):
        from PySide6.QtWidgets import QScrollArea, QFrame
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background: transparent;")
        widget.setStyleSheet("background: transparent;")
        from ui.theme import get_colors as _gc2
        _c2 = _gc2()
        _scrollbar_bg = "#4c3d99" if _c2.get("IS_DARK") else "#c7d2fe"
        _scrollbar_hover = "#7c6ecf" if _c2.get("IS_DARK") else "#818cf8"
        scroll.setStyleSheet(f"""
            QScrollArea, QScrollArea > QWidget, QAbstractScrollArea {{
                background: transparent;
                border: none;
            }}
            QWidget#qt_scrollarea_viewport {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 8px;
                margin: 0px 4px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {_scrollbar_bg};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_scrollbar_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                border: none;
                background: none;
            }}
        """)
        scroll.setWidget(widget)
        self._scroll_areas.append(scroll)
        return scroll

    def switch_tab(self, index):
        self.tab_stack.setCurrentIndex(index)
        if index == 3:
            self.populate_intruder_gallery()
        elif index == 4:
            self.populate_logs_table()

    def show_restart_banner(self):
        if self._loading:
            return
        self._has_pending_changes = True

    def restart_daemon(self):
        import psutil
        from utils.systemd_manager import restart, is_active
        from locking.launcher_sub import get_facegate_executable

        # 1. Try systemd first if the service is active or enabled
        if is_active():
            if restart():
                QMessageBox.information(self, "Restart Successful", "FaceGate daemon has been restarted successfully via systemd.")
                self.restart_banner.hide()
                return
            else:
                logging.warning("Systemd restart failed, trying manual fallback...")

        # 2. Manual fallback / non-systemd restart
        # Find any running facegate monitor processes
        daemon_procs = []
        for proc in psutil.process_iter(['cmdline']):
            try:
                cmd = proc.info['cmdline']
                # Ignore this settings window process (which might have --settings)
                if cmd and any('facegate' in part or 'monitor_main' in part for part in cmd) and any('--monitor' in part for part in cmd):
                    daemon_procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Terminate any existing manual monitor processes
        for proc in daemon_procs:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception as e:
                logging.warning(f"Could not cleanly terminate process: {e}. Killing.")
                try:
                    proc.kill()
                except Exception:
                    pass

        # Spawn a new facegate --monitor process in the background
        facegate_exe = get_facegate_executable()
        try:
            # We run it completely detached from the current settings window process
            # so that it survives when settings window closes!
            subprocess.Popen([facegate_exe, "--monitor"], close_fds=True, start_new_session=True)
            QMessageBox.information(self, "Restart Successful", "FaceGate daemon has been restarted successfully.")
            self.restart_banner.hide()
        except Exception as e:
            QMessageBox.critical(self, "Restart Failed", f"Failed to restart FaceGate daemon: {e}")

    # ------------------ Tab Creation Methods ------------------
    
    def create_locked_apps_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Locked Applications")
        from ui.theme import style_heading
        style_heading(header, 20)
        header.setProperty("heading_size", 20)
        self._themed_labels.append((header, "TEXT_PRIMARY"))
        layout.addWidget(header)

        desc = QLabel("Manage applications that trigger face recognition authentication on launch.")
        desc.setStyleSheet("font-size: 13px;")
        desc.setProperty("secondary", True)
        layout.addWidget(desc)

        # Table
        self.apps_table = QTableWidget()
        self.apps_table.setColumnCount(4)
        self.apps_table.setHorizontalHeaderLabels(["Application", "Executable & Desktop Info", "Show in Tray", "Action"])
        self.apps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.apps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.apps_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.apps_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.apps_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.apps_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.apps_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.apps_table.setWordWrap(True)
        self.apps_table.verticalHeader().setDefaultSectionSize(56)
        self.apps_table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.apps_table)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.add_app_btn = QPushButton("+ Add Application...")
        self.add_app_btn.clicked.connect(self.open_app_picker)
        
        self.remove_selected_btn = QPushButton("- Remove Selected")
        self.remove_selected_btn.setObjectName("removeSelectedBtn")
        self.remove_selected_btn.clicked.connect(self.remove_selected_apps)
        
        btn_layout.addWidget(self.add_app_btn)
        btn_layout.addWidget(self.remove_selected_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.tab_stack.addWidget(page)

    def create_authentication_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        from ui.theme import get_card_qss, style_heading, style_themed_label
        header = QLabel("Authentication & Primitives")
        style_heading(header, 20)
        header.setProperty("heading_size", 20)
        self._themed_labels.append((header, "TEXT_PRIMARY"))
        layout.addWidget(header)

        # Master Password Config Card (Accent Border)
        self.card_master_pwd = QWidget()
        self.card_master_pwd.setObjectName("card")
        self.card_master_pwd.setStyleSheet(get_card_qss("accent"))
        c1_layout = QVBoxLayout(self.card_master_pwd)
        c1_layout.setContentsMargins(16, 16, 16, 16)
        c1_layout.setSpacing(10)

        lbl1 = QLabel("Master Password")
        style_themed_label(lbl1, "HEADER_TEXT", "font-size: 15px; font-weight: bold;")
        lbl1.setProperty("extra_css", "font-size: 15px; font-weight: bold;")
        self._themed_labels.append((lbl1, "HEADER_TEXT"))
        c1_layout.addWidget(lbl1)

        lbl2 = QLabel("Configures the local master password that secures your face database envelope. "
                      "Updating the password will re-encrypt all credentials at rest under a new random KDF salt.")
        lbl2.setStyleSheet("font-size: 13px; border: none;")
        lbl2.setProperty("secondary", True)
        lbl2.setWordWrap(True)
        c1_layout.addWidget(lbl2)

        self.change_pwd_btn = QPushButton("Change Master Password...")
        self.change_pwd_btn.setObjectName("changePwdBtn")
        self.change_pwd_btn.clicked.connect(self.trigger_password_change)
        
        h_btn_layout = QHBoxLayout()
        h_btn_layout.addWidget(self.change_pwd_btn)
        h_btn_layout.addStretch()
        c1_layout.addLayout(h_btn_layout)
        
        layout.addWidget(self.card_master_pwd)

        # Enrolled Face Profiles & Admin Vault Card (Accent Border)
        self.card_enrolled = QWidget()
        self.card_enrolled.setObjectName("card")
        self.card_enrolled.setStyleSheet(get_card_qss("accent"))
        ce_layout = QVBoxLayout(self.card_enrolled)
        ce_layout.setContentsMargins(16, 16, 16, 16)
        ce_layout.setSpacing(12)

        ce_lbl = QLabel("👑 Biometric Access Control & Admin Vault")
        style_themed_label(ce_lbl, "HEADER_TEXT", "font-size: 15px; font-weight: bold;")
        ce_lbl.setProperty("extra_css", "font-size: 15px; font-weight: bold;")
        self._themed_labels.append((ce_lbl, "HEADER_TEXT"))
        ce_layout.addWidget(ce_lbl)

        self.enrolled_users_desc = QLabel(
            "Manage enrolled facial templates and administrative privileges. "
            "Only the Primary Admin (or Master Password holder) can modify or delete facial profiles."
        )
        self.enrolled_users_desc.setStyleSheet("font-size: 13px; border: none;")
        self.enrolled_users_desc.setProperty("secondary", True)
        self.enrolled_users_desc.setWordWrap(True)
        ce_layout.addWidget(self.enrolled_users_desc)

        # Enrolled users list with per-user action controls
        self.enrolled_users_container = QWidget()
        self.enrolled_users_layout = QVBoxLayout(self.enrolled_users_container)
        self.enrolled_users_layout.setContentsMargins(0, 0, 0, 0)
        self.enrolled_users_layout.setSpacing(8)
        ce_layout.addWidget(self.enrolled_users_container)

        self.enrolled_empty_label = QLabel("No enrolled faces registered in system vault.")
        self.enrolled_empty_label.setStyleSheet("color: #ef4444; font-size: 13px; font-style: italic; border: none;")
        self.enrolled_empty_label.hide()
        ce_layout.addWidget(self.enrolled_empty_label)

        # Action Buttons Bar
        enrolled_btn_layout = QHBoxLayout()
        enrolled_btn_layout.setSpacing(10)
        
        self.test_face_btn = QPushButton("🔍 Test Face Recognition")
        self.test_face_btn.setObjectName("testFaceBtn")
        self.test_face_btn.clicked.connect(self.run_face_verification_test)

        self.enroll_new_btn = QPushButton("➕ Enroll New Face")
        self.enroll_new_btn.setObjectName("enrollNewBtn")
        self.enroll_new_btn.clicked.connect(self.open_enrollment_wizard)

        enrolled_btn_layout.addWidget(self.test_face_btn)
        enrolled_btn_layout.addWidget(self.enroll_new_btn)
        enrolled_btn_layout.addStretch()
        ce_layout.addLayout(enrolled_btn_layout)
        
        layout.addWidget(self.card_enrolled)

        # Primitives Specs Card (Normal Border)
        self.card_security_profiles = QWidget()
        self.card_security_profiles.setObjectName("card")
        self.card_security_profiles.setStyleSheet(get_card_qss("normal"))
        c2_layout = QVBoxLayout(self.card_security_profiles)
        c2_layout.setContentsMargins(16, 16, 16, 16)
        c2_layout.setSpacing(12)

        lbl3 = QLabel("Active Security Profiles")
        style_themed_label(lbl3, "HEADER_TEXT", "font-size: 15px; font-weight: bold;")
        lbl3.setProperty("extra_css", "font-size: 15px; font-weight: bold;")
        self._themed_labels.append((lbl3, "HEADER_TEXT"))
        c2_layout.addWidget(lbl3)

        # Read-only attributes layout
        self.kdf_label = QLabel("KDF: PBKDF2-HMAC-SHA256 (600,000 iterations)")
        style_themed_label(self.kdf_label, "TEXT_PRIMARY", "font-size: 13px; border: none;")
        self.kdf_label.setProperty("extra_css", "font-size: 13px; border: none;")
        self._themed_labels.append((self.kdf_label, "TEXT_PRIMARY"))
        c2_layout.addWidget(self.kdf_label)

        self.cipher_label = QLabel("Cipher: AES-256-GCM (Authenticated Encrypt-then-MAC)")
        style_themed_label(self.cipher_label, "TEXT_PRIMARY", "font-size: 13px; border: none;")
        self.cipher_label.setProperty("extra_css", "font-size: 13px; border: none;")
        self._themed_labels.append((self.cipher_label, "TEXT_PRIMARY"))
        c2_layout.addWidget(self.cipher_label)

        # Load values dynamically from config
        thresh = self.config.get("recognition.similarity_threshold", "0.65")
        margin = self.config.get("recognition.ambiguity_margin", "0.03")

        self.thresh_label = QLabel(f"Similarity Threshold: {thresh} (Required matching score)")
        style_themed_label(self.thresh_label, "TEXT_PRIMARY", "font-size: 13px; border: none;")
        self.thresh_label.setProperty("extra_css", "font-size: 13px; border: none;")
        self._themed_labels.append((self.thresh_label, "TEXT_PRIMARY"))
        c2_layout.addWidget(self.thresh_label)

        self.margin_label = QLabel(f"Ambiguity Margin: {margin} (Required margin between top candidates)")
        style_themed_label(self.margin_label, "TEXT_PRIMARY", "font-size: 13px; border: none;")
        self.margin_label.setProperty("extra_css", "font-size: 13px; border: none;")
        self._themed_labels.append((self.margin_label, "TEXT_PRIMARY"))
        c2_layout.addWidget(self.margin_label)

        layout.addWidget(self.card_security_profiles)
        layout.addStretch()

        self.tab_stack.addWidget(self.wrap_in_scroll_area(page))

    def open_enrollment_wizard(self):
        if not self.verify_settings_action("Enroll New Face"):
            QMessageBox.warning(self, "Access Denied", "Admin verification failed. Enrollment cancelled.")
            return

        from ui.enrollment_wizard import EnrollmentWizard
        dialog = EnrollmentWizard(self)
        dialog.exec()
        # Refresh enrolled users list after enrollment wizard closes
        self.populate_enrolled_users()

    def create_behavior_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        from ui.theme import get_card_qss, AnimatedSpinBox, style_heading, style_themed_label
        header = QLabel("Daemon Behavior & Protection")
        style_heading(header, 20)
        header.setProperty("heading_size", 20)
        self._themed_labels.append((header, "TEXT_PRIMARY"))
        layout.addWidget(header)

        from PySide6.QtWidgets import QFormLayout

        # --- 1. Startup Group ---
        self.card_startup = QWidget()
        self.card_startup.setObjectName("card")
        self.card_startup.setStyleSheet(get_card_qss("normal"))
        startup_layout = QVBoxLayout(self.card_startup)
        startup_layout.setContentsMargins(16, 16, 16, 16)
        startup_layout.setSpacing(10)

        startup_lbl = QLabel("Startup Settings")
        style_themed_label(startup_lbl, "HEADER_TEXT", "font-size: 15px; font-weight: bold;")
        startup_lbl.setProperty("extra_css", "font-size: 15px; font-weight: bold;")
        self._themed_labels.append((startup_lbl, "HEADER_TEXT"))
        startup_layout.addWidget(startup_lbl)

        self.autostart_check = AnimatedCheckBox("Start FaceGate automatically when you log in")
        startup_layout.addWidget(self.autostart_check)

        delay_layout = QHBoxLayout()
        delay_lbl = QLabel("Delay before starting on boot (seconds):")
        delay_lbl.setStyleSheet("font-size: 13px;")
        delay_lbl.setProperty("secondary", True)
        self.delay_spin = AnimatedSpinBox()
        self.delay_spin.setRange(0, 60)
        delay_layout.addWidget(delay_lbl)
        delay_layout.addWidget(self.delay_spin)
        delay_layout.addStretch()
        startup_layout.addLayout(delay_layout)

        # Theme Selection
        theme_layout = QHBoxLayout()
        theme_lbl = QLabel("Application Theme Mode:")
        theme_lbl.setStyleSheet("font-size: 13px;")
        theme_lbl.setProperty("secondary", True)
        self.theme_combo = AnimatedComboBox()
        self.theme_combo.addItem("System Default Theme", "system")
        self.theme_combo.addItem("Light Theme Mode", "light")
        self.theme_combo.addItem("Dark Theme Mode", "dark")
        self.theme_combo.currentIndexChanged.connect(self.handle_theme_changed)
        theme_layout.addWidget(theme_lbl)
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()
        startup_layout.addLayout(theme_layout)

        layout.addWidget(self.card_startup)

        # --- 2. Locking Policy Group ---
        self.card_policy = QWidget()
        self.card_policy.setObjectName("card")
        self.card_policy.setStyleSheet(get_card_qss("normal"))
        policy_layout = QVBoxLayout(self.card_policy)
        policy_layout.setContentsMargins(16, 16, 16, 16)
        policy_layout.setSpacing(10)

        policy_lbl = QLabel("Security & Scanning Policies")
        style_themed_label(policy_lbl, "HEADER_TEXT", "font-size: 15px; font-weight: bold;")
        policy_lbl.setProperty("extra_css", "font-size: 15px; font-weight: bold;")
        self._themed_labels.append((policy_lbl, "HEADER_TEXT"))
        policy_layout.addWidget(policy_lbl)

        policy_form = QFormLayout()
        policy_form.setSpacing(10)
        policy_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.policy_combo = AnimatedComboBox()
        self.policy_combo.addItem("Close and exit the locked application immediately (Recommended)", "kill")
        self.policy_combo.addItem("Freeze the application in the background", "keep_stopped")
        policy_form.addRow("If authentication is cancelled or fails:", self.policy_combo)

        self.timeout_spin = AnimatedSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSingleStep(5)
        policy_form.addRow("Close face scan screen after (seconds):", self.timeout_spin)

        policy_layout.addLayout(policy_form)
        layout.addWidget(self.card_policy)

        # --- 3. Protection Group (Danger Red Highlight) ---
        self.card_protection = QWidget()
        self.card_protection.setObjectName("card")
        self.card_protection.setStyleSheet(get_card_qss("danger"))
        prot_layout = QVBoxLayout(self.card_protection)
        prot_layout.setContentsMargins(16, 16, 16, 16)
        prot_layout.setSpacing(10)

        prot_lbl = QLabel("Self-Protection & Emergency Override")
        prot_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #ef4444;")
        prot_layout.addWidget(prot_lbl)

        self.protection_check = AnimatedCheckBox("Enable anti-uninstall protection (Recommended)")
        self.protection_check.clicked.connect(self.handle_protection_clicked)
        prot_layout.addWidget(self.protection_check)
        
        prot_desc = QLabel("Prevents unauthorized users from deleting FaceGate settings or bypassing protection.")
        prot_desc.setStyleSheet("font-size: 11px; margin-left: 20px; border: none; background: transparent;")
        prot_desc.setProperty("secondary", True)
        prot_layout.addWidget(prot_desc)

        hk_layout = QHBoxLayout()
        hk_lbl = QLabel("Emergency Shutdown Shortcut:")
        hk_lbl.setStyleSheet("font-size: 13px;")
        hk_lbl.setProperty("secondary", True)
        self.hotkey_input = QLineEdit()
        self.hotkey_input.setPlaceholderText("<Control><Alt>k")
        hk_layout.addWidget(hk_lbl)
        hk_layout.addWidget(self.hotkey_input)
        hk_layout.addStretch()
        prot_layout.addLayout(hk_layout)

        hk_desc = QLabel("Press this keyboard combination to immediately stop FaceGate and restore all apps in case of camera failure. Format: e.g. <Control><Alt>k")
        hk_desc.setStyleSheet("font-size: 11px; font-style: italic; margin-bottom: 5px;")
        hk_desc.setProperty("secondary", True)
        hk_desc.setWordWrap(True)
        prot_layout.addWidget(hk_desc)

        panic_hk_layout = QHBoxLayout()
        panic_hk_lbl = QLabel("Panic Lockdown Shortcut:")
        panic_hk_lbl.setStyleSheet("font-size: 13px;")
        panic_hk_lbl.setProperty("secondary", True)
        self.panic_hotkey_input = QLineEdit()
        self.panic_hotkey_input.setPlaceholderText("<Control><Alt>l")
        panic_hk_layout.addWidget(panic_hk_lbl)
        panic_hk_layout.addWidget(self.panic_hotkey_input)
        panic_hk_layout.addStretch()
        prot_layout.addLayout(panic_hk_layout)

        panic_hk_desc = QLabel("Press this keyboard combination to immediately lock all running protected applications to prevent trespassing. Format: e.g. <Control><Alt>l")
        panic_hk_desc.setStyleSheet("font-size: 11px; font-style: italic;")
        panic_hk_desc.setProperty("secondary", True)
        panic_hk_desc.setWordWrap(True)
        prot_layout.addWidget(panic_hk_desc)

        layout.addWidget(self.card_protection)

        # --- 4. Notifications & Idle Group ---
        self.card_notifications = QWidget()
        self.card_notifications.setObjectName("card")
        self.card_notifications.setStyleSheet(get_card_qss("normal"))
        notif_layout = QVBoxLayout(self.card_notifications)
        notif_layout.setContentsMargins(16, 16, 16, 16)
        notif_layout.setSpacing(10)

        notif_lbl = QLabel("Notifications & Auto-Locking")
        style_themed_label(notif_lbl, "HEADER_TEXT", "font-size: 15px; font-weight: bold;")
        notif_lbl.setProperty("extra_css", "font-size: 15px; font-weight: bold;")
        self._themed_labels.append((notif_lbl, "HEADER_TEXT"))
        notif_layout.addWidget(notif_lbl)

        self.notify_check = AnimatedCheckBox("Show desktop notification banners on successful unlocks")
        notif_layout.addWidget(self.notify_check)

        self.idle_check = AnimatedCheckBox("Automatically lock open applications when system becomes idle")
        notif_layout.addWidget(self.idle_check)

        idle_time_layout = QHBoxLayout()
        idle_time_lbl = QLabel("System idle time before locking (minutes):")
        idle_time_lbl.setStyleSheet("font-size: 13px;")
        idle_time_lbl.setProperty("secondary", True)
        self.idle_spin = AnimatedSpinBox()
        self.idle_spin.setRange(1, 60)
        self.idle_spin.setEnabled(False)
        self.idle_check.stateChanged.connect(lambda state: self.idle_spin.setEnabled(state == Qt.CheckState.Checked.value))
        idle_time_layout.addWidget(idle_time_lbl)
        idle_time_layout.addWidget(self.idle_spin)
        idle_time_layout.addStretch()
        notif_layout.addLayout(idle_time_layout)

        self.sleep_lock_check = AnimatedCheckBox("Automatically lock all open applications when the system sleeps or locks (Recommended)")
        notif_layout.addWidget(self.sleep_lock_check)

        self.lock_settings_check = AnimatedCheckBox("Require face/password verification to open settings window (Recommended)")
        notif_layout.addWidget(self.lock_settings_check)

        layout.addWidget(self.card_notifications)
        layout.addStretch()

        self.tab_stack.addWidget(self.wrap_in_scroll_area(page))

    def create_logs_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Security Audit Logs")
        from ui.theme import style_heading
        style_heading(header, 20)
        header.setProperty("heading_size", 20)
        self._themed_labels.append((header, "TEXT_PRIMARY"))
        layout.addWidget(header)

        desc = QLabel("View recent application authorization attempts and outcomes.")
        desc.setStyleSheet("font-size: 13px;")
        desc.setProperty("secondary", True)
        layout.addWidget(desc)

        # Filter Chips/Dropdown Layout
        filter_layout = QHBoxLayout()
        filter_lbl = QLabel("Filter status:")
        filter_lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        filter_lbl.setProperty("secondary", True)
        
        self.log_filter_combo = AnimatedComboBox()
        self.log_filter_combo.addItems(["All Attempts", "Success", "Failed", "Timeout", "Bypass"])
        self.log_filter_combo.currentIndexChanged.connect(self.populate_logs_table)
        
        filter_layout.addWidget(filter_lbl)
        filter_layout.addWidget(self.log_filter_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Tree Widget for logs
        self.logs_tree = QTreeWidget()
        self.logs_tree.setColumnCount(6)
        self.logs_tree.setHeaderLabels(["Time", "Application", "Method", "User", "Result", "Confidence"])
        self.logs_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.logs_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.header().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        layout.addWidget(self.logs_tree)

        # Empty state label
        self.logs_empty_label = QLabel("No authentication activity yet")
        self.logs_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logs_empty_label.setStyleSheet("font-size: 14px; font-style: italic; padding: 40px;")
        self.logs_empty_label.setProperty("secondary", True)
        layout.addWidget(self.logs_empty_label)
        self.logs_empty_label.hide()

        # Export CSV button
        export_layout = QHBoxLayout()
        export_layout.addStretch()
        self.export_csv_btn = QPushButton("📥 Export as CSV")
        self.export_csv_btn.setObjectName("exportCsvBtn")
        self.export_csv_btn.clicked.connect(self.export_audit_logs_csv)
        export_layout.addWidget(self.export_csv_btn)
        layout.addLayout(export_layout)

        self.tab_stack.addWidget(page)

    def create_about_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        from ui.theme import get_card_qss, style_heading, style_themed_label
        header = QLabel("About FaceGate-Linux")
        style_heading(header, 20)
        header.setProperty("heading_size", 20)
        self._themed_labels.append((header, "TEXT_PRIMARY"))
        layout.addWidget(header)

        self.card_about = QWidget()
        self.card_about.setObjectName("card")
        self.card_about.setStyleSheet(get_card_qss("normal"))
        card_layout = QVBoxLayout(self.card_about)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        logo = QLabel("🔒 FaceGate-Linux")
        style_themed_label(logo, "ACCENT_PURPLE", "font-size: 24px; font-weight: bold; border: none;")
        logo.setProperty("extra_css", "font-size: 24px; font-weight: bold; border: none;")
        self._themed_labels.append((logo, "ACCENT_PURPLE"))
        card_layout.addWidget(logo)

        version = QLabel("Version: 1.0.0 (Production Release)")
        style_themed_label(version, "TEXT_PRIMARY", "font-size: 13px; border: none; font-weight: bold;")
        version.setProperty("extra_css", "font-size: 13px; border: none; font-weight: bold;")
        self._themed_labels.append((version, "TEXT_PRIMARY"))
        card_layout.addWidget(version)

        desc = QLabel("FaceGate-Linux is a lightweight security wrapper daemon that locks system application launches "
                      "using face recognition. It combines process scanning, SIGSTOP interception, D-Bus session controls, "
                      "and authenticated AES-256-GCM data storage.")
        style_themed_label(desc, "TEXT_SECONDARY", "font-size: 13px; border: none; line-height: 1.4;")
        desc.setProperty("extra_css", "font-size: 13px; border: none; line-height: 1.4;")
        desc.setWordWrap(True)
        self._themed_labels.append((desc, "TEXT_SECONDARY"))
        card_layout.addWidget(desc)

        card_layout.addSpacing(10)
        
        info = QLabel("Created by voidnode.")
        style_themed_label(info, "TEXT_SECONDARY", "font-size: 12px; border: none; font-style: italic;")
        info.setProperty("extra_css", "font-size: 12px; border: none; font-style: italic;")
        self._themed_labels.append((info, "TEXT_SECONDARY"))
        card_layout.addWidget(info)

        layout.addWidget(self.card_about)
        layout.addStretch()

        self.tab_stack.addWidget(page)

    # ------------------ Loading Settings ------------------
    
    def load_settings(self):
        self._loading = True  # Suppress restart banner during load
        # 1. Apps Table
        self.populate_apps_table()
        
        # 2. Behavior
        policy = self.config.get("app_monitor.on_auth_failure", "kill")
        idx = self.policy_combo.findData(policy)
        if idx >= 0:
            self.policy_combo.setCurrentIndex(idx)
            
        timeout = self.config.get("app_monitor.auth_timeout_seconds", 60)
        self.timeout_spin.setValue(timeout)
        
        # 3. Autostart & Protection
        self.autostart_check.setChecked(is_enabled())
        self.protection_check.setChecked(self.config.get("behavior.uninstall_protection", True))
        
        # 4. Emergency Kill Hotkey
        hotkey = self.config.get("behavior.emergency_key", "<Control><Alt>k")
        self.hotkey_input.setText(hotkey)

        # 4b. Panic Lockdown Hotkey
        panic_hotkey = self.config.get("behavior.panic_key", "<Control><Alt>l")
        self.panic_hotkey_input.setText(panic_hotkey)

        # 5. New behavior settings
        self.notify_check.setChecked(self.config.get("behavior.notify_on_auth", True))
        self.idle_check.setChecked(self.config.get("behavior.autolock_on_idle", False))
        self.idle_spin.setValue(self.config.get("behavior.autolock_on_idle_minutes", 10))
        self.idle_spin.setEnabled(self.idle_check.isChecked())
        self.delay_spin.setValue(self.config.get("behavior.startup_delay_seconds", 0))
        
        self.theme_combo.blockSignals(True)
        theme_val = self.config.get("behavior.theme", "system")
        theme_idx = self.theme_combo.findData(theme_val)
        if theme_idx >= 0:
            self.theme_combo.setCurrentIndex(theme_idx)
        self.theme_combo.blockSignals(False)
        
        self.sleep_lock_check.setChecked(self.config.get("behavior.lock_on_sleep_or_lock", True))
        self.lock_settings_check.setChecked(self.config.get("security.lock_settings_window", True))

        # 6. Load enrolled users list dynamically
        self.populate_enrolled_users()

        # 7. Populate Logs Table
        self.populate_logs_table()

        # 8. Populate Intruder Gallery
        self.populate_intruder_gallery()

        # 9. Update sidebar enrolled count badge
        self._update_sidebar_enrolled_count()

        # Connect signals for restart indicator ONCE (guard prevents duplicates)
        if not self._signals_connected:
            self._signals_connected = True
            self.policy_combo.currentIndexChanged.connect(self.show_restart_banner)
            self.timeout_spin.valueChanged.connect(self.show_restart_banner)
            self.protection_check.stateChanged.connect(self.show_restart_banner)
            self.hotkey_input.textChanged.connect(self.show_restart_banner)
            self.panic_hotkey_input.textChanged.connect(self.show_restart_banner)
            self.notify_check.stateChanged.connect(self.show_restart_banner)
            self.idle_check.stateChanged.connect(self.show_restart_banner)
            self.idle_spin.valueChanged.connect(self.show_restart_banner)
            self.delay_spin.valueChanged.connect(self.show_restart_banner)
            self.sleep_lock_check.stateChanged.connect(self.show_restart_banner)
            self.lock_settings_check.stateChanged.connect(self.show_restart_banner)

        self._loading = False

    def populate_enrolled_users(self):
        """Populates the enrolled users list with Admin badges and per-user actions."""
        from ui.theme import get_colors
        c = get_colors()

        # Clear existing items
        while self.enrolled_users_layout.count():
            item = self.enrolled_users_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Fetch enrolled usernames (try database store first, fallback to D-Bus)
        usernames = []
        try:
            from database.embedding_store import load_embeddings
            enrolled = load_embeddings()
            if enrolled:
                usernames = list(enrolled.keys())
        except Exception:
            usernames = []

        if not usernames:
            try:
                from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusReply
                bus = QDBusConnection.sessionBus()
                if bus.isConnected():
                    interface = QDBusInterface(
                        "org.facegate.FaceGate",
                        "/org/facegate/FaceGate",
                        "org.facegate.FaceGate",
                        bus
                    )
                    if interface.isValid():
                        raw_reply = interface.call("GetEnrolledUsers")
                        reply = QDBusReply(raw_reply)
                        if reply.isValid():
                            users_str = reply.value()
                            if users_str:
                                usernames = [u for u in users_str.split(",") if u]
            except Exception as e:
                logging.error(f"Failed to load enrolled users list via D-Bus: {e}")

        if not usernames:
            self.enrolled_empty_label.show()
            self._update_sidebar_enrolled_count()
            return

        self.enrolled_empty_label.hide()

        from database.embedding_store import get_admin_user
        admin_user = get_admin_user()

        bg_sec = c.get("BG_SECONDARY", c.get("WIDGET_BG", "#1f1d29"))
        border_n = c.get("BORDER_NEUTRAL", "#2c2a38")
        hover_n = c.get("HOVER_NEUTRAL", c.get("LIST_ITEM_HOVER", "#312e43"))
        text_p = c.get("TEXT_PRIMARY", "#e2e1e9")
        text_s = c.get("TEXT_SECONDARY", "#a5a3b4")
        accent_p = c.get("ACCENT_PURPLE", "#a855f7")

        for username in usernames:
            is_admin = (username == admin_user)

            row_widget = QWidget()
            row_widget.setObjectName("userRowWidget")
            row_widget.setStyleSheet(f"""
                QWidget#userRowWidget {{
                    background-color: {bg_sec};
                    border: 1px solid {border_n};
                    border-radius: 8px;
                }}
            """)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(10)

            user_icon_lbl = QLabel("👑" if is_admin else "👤")
            user_icon_lbl.setStyleSheet("font-size: 18px; border: none; background: transparent;")
            row_layout.addWidget(user_icon_lbl)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)

            name_lbl = QLabel(username)
            name_lbl.setStyleSheet(f"color: {text_p}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
            info_layout.addWidget(name_lbl)

            role_text = "👑 Primary Admin & Vault Owner" if is_admin else "👤 Enrolled Profile"
            role_color = accent_p if is_admin else text_s
            role_lbl = QLabel(role_text)
            role_lbl.setStyleSheet(f"color: {role_color}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
            info_layout.addWidget(role_lbl)

            # Last verified timestamp from audit log
            last_auth_text = self._get_last_auth_time(username)
            if last_auth_text:
                last_auth_lbl = QLabel(f"🕐 {last_auth_text}")
                last_auth_lbl.setStyleSheet(f"color: {text_s}; font-size: 10px; border: none; background: transparent;")
                info_layout.addWidget(last_auth_lbl)

            row_layout.addLayout(info_layout)
            row_layout.addStretch()

            # Actions
            if not is_admin:
                make_admin_btn = QPushButton("Make Admin")
                make_admin_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {accent_p};
                        border: 1px solid {accent_p};
                        border-radius: 6px;
                        padding: 4px 10px;
                        font-size: 11px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {accent_p};
                        color: white;
                    }}
                """)
                make_admin_btn.clicked.connect(self._make_set_admin_callback(username))
                row_layout.addWidget(make_admin_btn)

            reenroll_btn = QPushButton("Re-Enroll")
            cancel_bg = c.get("CANCEL_BTN_BG", "#25213b")
            reenroll_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {cancel_bg};
                    color: {text_p};
                    border: 1px solid {border_n};
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {hover_n};
                }}
            """)
            reenroll_btn.clicked.connect(self._make_reenroll_callback(username))
            row_layout.addWidget(reenroll_btn)

            delete_btn = QPushButton("Delete")
            delete_btn.setObjectName("removeBtn")
            delete_btn.setStyleSheet("""
                QPushButton#removeBtn {
                    background-color: #ef4444;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton#removeBtn:hover {
                    background-color: #dc2626;
                }
            """)
            delete_btn.clicked.connect(self._make_remove_enrolled_callback(username))
            row_layout.addWidget(delete_btn)

            self.enrolled_users_layout.addWidget(row_widget)

        self._update_sidebar_enrolled_count()

    def _make_remove_enrolled_callback(self, username):
        return lambda: self._remove_enrolled_user(username)

    def _make_set_admin_callback(self, username):
        return lambda: self._set_primary_admin(username)

    def _make_reenroll_callback(self, username):
        return lambda: self._reenroll_user(username)

    def _get_last_auth_time(self, username: str) -> str:
        """Returns a human-readable 'Last verified: X ago' string for a given user from the audit log."""
        try:
            from database.audit_log import get_recent_logs
            import datetime
            from datetime import timezone
            logs = get_recent_logs(200)
            for log in logs:
                if log.get("username") == username and log.get("result", "").lower() == "success":
                    ts_str = str(log["timestamp"])
                    clean_ts = ts_str.split(".")[0].replace("Z", "").split("+")[0]
                    utc_dt = datetime.datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    local_dt = utc_dt.astimezone()
                    now = datetime.datetime.now(tz=local_dt.tzinfo)
                    delta = now - local_dt
                    if delta.total_seconds() < 60:
                        return "Last verified: just now"
                    elif delta.total_seconds() < 3600:
                        mins = int(delta.total_seconds() / 60)
                        return f"Last verified: {mins} min{'s' if mins != 1 else ''} ago"
                    elif delta.total_seconds() < 86400:
                        hours = int(delta.total_seconds() / 3600)
                        return f"Last verified: {hours} hour{'s' if hours != 1 else ''} ago"
                    else:
                        days = int(delta.total_seconds() / 86400)
                        return f"Last verified: {days} day{'s' if days != 1 else ''} ago"
        except Exception:
            pass
        return ""

    def _update_sidebar_enrolled_count(self):
        """Updates the Authentication sidebar item with an enrolled user count badge."""
        try:
            # Count enrolled users
            count = 0
            try:
                from database.embedding_store import load_embeddings
                enrolled = load_embeddings()
                count = len(enrolled)
            except Exception:
                pass

            auth_item = self.sidebar.item(1)  # "Authentication" is index 1
            if auth_item:
                if count > 0:
                    auth_item.setText(f"Authentication ({count})")
                else:
                    auth_item.setText("Authentication")
        except Exception as e:
            logging.error(f"Error updating sidebar enrolled count: {e}")

    def export_audit_logs_csv(self):
        """Exports filtered audit logs to a CSV file."""
        from PySide6.QtWidgets import QFileDialog
        import csv
        import datetime

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Audit Logs", 
            os.path.expanduser(f"~/facegate_audit_logs_{datetime.date.today().isoformat()}.csv"),
            "CSV Files (*.csv)"
        )
        if not filepath:
            return

        try:
            from database.audit_log import get_recent_logs
            logs = get_recent_logs(500)

            # Apply current filter
            filter_text = self.log_filter_combo.currentText().lower()
            if filter_text != "all attempts":
                filter_map = {"success": "success", "failed": "fail", "timeout": "timeout", "bypass": "bypass"}
                target = filter_map.get(filter_text, "")
                logs = [l for l in logs if l["result"].lower() == target]

            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Application", "Method", "User", "Result", "Confidence"])
                for log in logs:
                    writer.writerow([
                        log.get("timestamp", ""),
                        log.get("app_identifier", ""),
                        log.get("method", ""),
                        log.get("username", "N/A"),
                        log.get("result", ""),
                        f"{log['confidence_score']:.4f}" if log.get("confidence_score") is not None else "N/A"
                    ])

            QMessageBox.information(self, "Export Complete", f"Audit logs exported successfully to:\n{filepath}")
            logging.info(f"Audit logs exported to {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export audit logs: {e}")
            logging.error(f"Failed to export audit logs: {e}")

    def _remove_enrolled_user(self, username):
        """Remove a specific enrolled user after verification."""
        from ui.theme import get_colors
        c = get_colors()

        from database.embedding_store import get_admin_user
        admin_user = get_admin_user()
        is_admin = (username == admin_user)

        admin_warning = ""
        if is_admin:
            admin_warning = (
                "\n\n⚠️ WARNING: This user is currently the Primary Admin! "
                "Deleting them will automatically re-assign Admin privileges to another enrolled profile, "
                "or revert FaceGATE to Master Password authentication if no faces remain."
            )

        # Confirm removal
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Delete Enrolled Face Profile")
        msg_box.setText(
            f"Are you sure you want to permanently delete the facial profile for '{username}'?{admin_warning}"
        )
        msg_box.setIcon(QMessageBox.Icon.Warning)

        yes_btn = msg_box.addButton("Delete Profile", QMessageBox.ButtonRole.YesRole)
        no_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)

        yes_btn.setStyleSheet("background-color: #ef4444; color: white; padding: 6px 16px; font-weight: bold; border-radius: 6px; border: none;")
        no_btn.setStyleSheet(f"background-color: {c['CANCEL_BTN_BG']}; color: {c['TEXT_PRIMARY']}; border: 1px solid {c['BORDER_NEUTRAL']}; padding: 6px 16px; font-weight: bold; border-radius: 6px;")

        msg_box.exec()
        if msg_box.clickedButton() != yes_btn:
            return

        # Require Admin verification before removing
        if not self.verify_settings_action(f"Delete Enrolled Face Profile for '{username}'"):
            QMessageBox.warning(self, "Access Denied", "Admin verification failed. Profile was not deleted.")
            return

        # Perform removal
        try:
            from database.embedding_store import delete_embedding
            delete_embedding(username)
            QMessageBox.information(self, "Profile Deleted", f"Facial profile for '{username}' has been deleted.")
            self.populate_enrolled_users()
            logging.info(f"Enrolled user '{username}' deleted successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Deletion Failed", f"Failed to delete facial profile: {e}")
            logging.error(f"Failed to delete facial profile for '{username}': {e}")

    def _set_primary_admin(self, username):
        from ui.theme import get_colors
        c = get_colors()

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Promote to Primary Admin")
        msg_box.setText(f"Do you want to designate '{username}' as the Primary Admin for FaceGATE?")
        msg_box.setIcon(QMessageBox.Icon.Question)

        yes_btn = msg_box.addButton("Promote to Admin", QMessageBox.ButtonRole.YesRole)
        no_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)

        yes_btn.setStyleSheet(f"background-color: {c['ACCENT_PURPLE']}; color: white; padding: 6px 16px; font-weight: bold; border-radius: 6px; border: none;")
        no_btn.setStyleSheet(f"background-color: {c['CANCEL_BTN_BG']}; color: {c['TEXT_PRIMARY']}; border: 1px solid {c['BORDER_NEUTRAL']}; padding: 6px 16px; font-weight: bold; border-radius: 6px;")

        msg_box.exec()
        if msg_box.clickedButton() != yes_btn:
            return

        if not self.verify_settings_action(f"Set '{username}' as Primary Admin"):
            QMessageBox.warning(self, "Access Denied", "Admin verification failed.")
            return

        try:
            from database.embedding_store import set_admin_user
            set_admin_user(username)
            QMessageBox.information(self, "Admin Set", f"'{username}' is now the Primary Admin.")
            self.populate_enrolled_users()
        except Exception as e:
            QMessageBox.critical(self, "Failed", f"Could not set admin: {e}")

    def _reenroll_user(self, username):
        if not self.verify_settings_action(f"Re-Enroll Face Profile for '{username}'"):
            QMessageBox.warning(self, "Access Denied", "Admin verification failed. Re-enrollment cancelled.")
            return

        from ui.enrollment_wizard import EnrollmentWizard
        dialog = EnrollmentWizard(self, target_username=username)
        dialog.exec()
        self.populate_enrolled_users()

    def run_face_verification_test(self):
        dialog = FaceVerificationTestDialog(self)
        dialog.exec()

    def populate_apps_table(self):
        self.apps_table.setRowCount(len(self.current_apps))
        for row, app in enumerate(self.current_apps):
            # Resolve QIcon using shared utility
            from ui.theme import resolve_app_icon
            icon = resolve_app_icon(app.get("icon", ""))
            
            icon_item = QTableWidgetItem(app.get("name", ""))
            icon_item.setIcon(icon)
            
            # Show executable path and desktop file info
            exec_name = app.get('executable', '')
            desktop_name = app.get('desktop_name', '')
            details_text = f"⚙️ Exec: {exec_name}"
            if desktop_name:
                details_text += f"\n📄 Desktop: {desktop_name}"
                
            details_item = QTableWidgetItem(details_text)
            details_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            details_item.setToolTip(f"Executable: {exec_name}\nDesktop File: {desktop_name or 'N/A'}\nApp ID: {app.get('id', '')}")
            
            # Checkbox for Show in Tray
            checkbox_widget = QWidget()
            checkbox_widget.setStyleSheet("background: transparent;")
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox = AnimatedCheckBox()
            checkbox.setChecked(app.get("show_in_tray", True))
            checkbox.stateChanged.connect(lambda state, a_id=app["id"], cb=checkbox: self.handle_tray_toggle(a_id, state, cb))
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            
            # Action Remove Button using app_id instead of row index to prevent indexing glitches
            action_widget = QWidget()
            action_widget.setStyleSheet("background: transparent;")
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 4, 4, 4)
            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("removeBtn")
            remove_btn.setStyleSheet("background-color: #ef4444; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-weight: bold;")
            remove_btn.clicked.connect(lambda checked=False, a_id=app["id"]: self.remove_app_by_id(a_id))
            action_layout.addWidget(remove_btn)
            action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Set items with ItemIsSelectable flag removed for columns 2 and 3
            item2 = QTableWidgetItem()
            item2.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item3 = QTableWidgetItem()
            item3.setFlags(Qt.ItemFlag.ItemIsEnabled)

            self.apps_table.setItem(row, 0, icon_item)
            self.apps_table.setItem(row, 1, details_item)
            self.apps_table.setItem(row, 2, item2)
            self.apps_table.setItem(row, 3, item3)
            self.apps_table.setCellWidget(row, 2, checkbox_widget)
            self.apps_table.setCellWidget(row, 3, action_widget)

    def handle_tray_toggle(self, app_id, state, checkbox):
        checked = (state == Qt.CheckState.Checked.value)
        if checked:
            # Count other apps with show_in_tray enabled
            active_count = sum(1 for a in self.current_apps if a.get("show_in_tray", True) and a["id"] != app_id)
            if active_count >= 5:
                from ui.theme import get_colors
                c = get_colors()
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Tray Limit Reached")
                msg_box.setText("You can display a maximum of 5 applications in the system tray.\n\n"
                                "Please uncheck another application first to display this one.")
                msg_box.setIcon(QMessageBox.Icon.Warning)
                ok_btn = msg_box.addButton(QMessageBox.StandardButton.Ok)
                ok_btn.setStyleSheet(f"background-color: {c['ACCENT_PURPLE']}; color: white; padding: 6px 16px; min-width: 80px; font-weight: bold; border-radius: 6px; border: none;")
                
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)
                
                msg_box.exec()
                return
                
        # Save state to current_apps
        for app in self.current_apps:
            if app["id"] == app_id:
                app["show_in_tray"] = checked
                break
                
        self.show_restart_banner()

    def remove_app_by_id(self, app_id):
        self.current_apps = [a for a in self.current_apps if a["id"] != app_id]
        self.populate_apps_table()
        self.show_restart_banner()
        logging.info(f"Staged app removal: '{app_id}'")

    def remove_selected_apps(self):
        selected_ranges = self.apps_table.selectedRanges()
        if not selected_ranges:
            QMessageBox.information(self, "No Selection", "Please select one or more applications from the table to remove.")
            return
            
        # Identify all row indices to remove
        rows_to_remove = set()
        for r in selected_ranges:
            for row in range(r.topRow(), r.bottomRow() + 1):
                rows_to_remove.add(row)
                
        if not rows_to_remove:
            return
            
        # Map row indices to application IDs
        ids_to_remove = [self.current_apps[row]["id"] for row in rows_to_remove if row < len(self.current_apps)]
        
        # Perform removals
        self.current_apps = [a for a in self.current_apps if a["id"] not in ids_to_remove]
        self.populate_apps_table()
        self.show_restart_banner()
        logging.info(f"Staged removal of selected apps: {ids_to_remove}")

    def populate_logs_table(self):
        from database.audit_log import get_recent_logs
        from ui.theme import create_status_icon, SUCCESS_GREEN, DANGER_RED, WARNING_AMBER
        import datetime

        # Clear tree
        self.logs_tree.clear()

        # Get filter
        filter_text = self.log_filter_combo.currentText().lower()
        
        logs = get_recent_logs(100)
        
        filtered_logs = []
        for log in logs:
            res_lower = log["result"].lower()
            if filter_text == "all attempts":
                filtered_logs.append(log)
            elif filter_text == "success" and res_lower == "success":
                filtered_logs.append(log)
            elif filter_text == "failed" and res_lower == "fail":
                filtered_logs.append(log)
            elif filter_text == "timeout" and res_lower == "timeout":
                filtered_logs.append(log)
            elif filter_text == "bypass" and res_lower == "bypass":
                filtered_logs.append(log)

        filtered_logs = filtered_logs[:50]

        if not filtered_logs:
            self.logs_tree.hide()
            self.logs_empty_label.show()
            return
        
        self.logs_empty_label.hide()
        self.logs_tree.show()

        # Group by day
        grouped = {}
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        for log in filtered_logs:
            ts_str = str(log["timestamp"])
            try:
                clean_ts = ts_str.split(".")[0].replace("Z", "").split("+")[0]
                from datetime import timezone
                utc_dt = datetime.datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                local_dt = utc_dt.astimezone()
                date_part = local_dt.strftime("%Y-%m-%d")
                time_part = local_dt.strftime("%H:%M:%S")
            except Exception:
                parts = ts_str.split(" ")
                date_part = parts[0]
                time_part = parts[1] if len(parts) > 1 else ""

            if date_part == today_str:
                group_key = "Today"
            elif date_part == yesterday_str:
                group_key = "Yesterday"
            else:
                group_key = date_part

            if group_key not in grouped:
                grouped[group_key] = []
            grouped[group_key].append((time_part, log))

        # Populate tree
        for date_header, items in grouped.items():
            header_item = QTreeWidgetItem([date_header])
            header_item.setFirstColumnSpanned(True)
            header_item.setFlags(header_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            
            font = header_item.font(0)
            font.setBold(True)
            header_item.setFont(0, font)
            self.logs_tree.addTopLevelItem(header_item)

            for time_part, log in items:
                app_identifier = log["app_identifier"]
                method = log["method"].upper()
                username = log.get("username") or "N/A"
                res = log["result"].upper()
                score_str = f"{log['confidence_score']:.4f}" if log["confidence_score"] is not None else "N/A"

                child_item = QTreeWidgetItem([
                    time_part,
                    app_identifier,
                    method,
                    username,
                    res,
                    score_str
                ])

                res_lower = log["result"].lower()
                if res_lower == "success":
                    icon_color = SUCCESS_GREEN
                elif res_lower == "timeout":
                    icon_color = "#3b82f6"
                elif res_lower == "bypass":
                    icon_color = WARNING_AMBER
                else:
                    icon_color = DANGER_RED
                child_item.setIcon(4, create_status_icon(icon_color))

                header_item.addChild(child_item)

        self.logs_tree.expandAll()

    # ------------------ Actions ------------------

    def open_app_picker(self):
        dialog = AppPickerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_app:
            app_data = dialog.selected_app
            
            show_in_tray_count = sum(1 for a in self.current_apps if a.get("show_in_tray", True))
            new_app = {
                "id": app_data["executable"],
                "name": app_data["name"],
                "executable": app_data["executable"],
                "desktop_name": app_data["desktop_name"],
                "show_in_tray": (show_in_tray_count < 5)
            }
            
            if app_data.get("icon"):
                new_app["icon"] = app_data["icon"]
                
            if any(a["id"] == new_app["id"] for a in self.current_apps):
                QMessageBox.warning(self, "Duplicate Application", 
                                    f"The application '{new_app['name']}' is already protected.")
                return
                
            self.current_apps.append(new_app)
            self.populate_apps_table()
            self.show_restart_banner()
            logging.info(f"Staged app protection addition: '{new_app['id']}'")

    def handle_theme_changed(self):
        new_theme = self.theme_combo.itemData(self.theme_combo.currentIndex())
        self.theme_mode = new_theme
        self.config.set("behavior.theme", new_theme)
        self.config.set("ui.theme", new_theme)
        self.apply_theme_dynamically()
        self._loading = True  # Suppress restart banner during theme refresh
        self.populate_enrolled_users()
        self.populate_apps_table()
        self.populate_logs_table()
        self.populate_intruder_gallery()
        self._update_sidebar_enrolled_count()
        self._loading = False
        self._has_pending_changes = True
        self.show_restart_banner()

    def verify_settings_action(self, reason: str) -> bool:
        # Check if we are running directly inside the daemon process that owns org.facegate.FaceGate
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusReply
            bus = QDBusConnection.sessionBus()
            is_self_daemon = False
            if bus.isConnected():
                try:
                    owner_reply = bus.interface().serviceOwner("org.facegate.FaceGate")
                    if owner_reply.isValid() and owner_reply.value() == bus.baseService():
                        is_self_daemon = True
                except Exception:
                    pass

            if is_self_daemon:
                from database.embedding_store import get_cached_key
                if get_cached_key():
                    return True
                from PySide6.QtWidgets import QApplication
                app_inst = QApplication.instance()
                if hasattr(app_inst, "verify_admin_face"):
                    return app_inst.verify_admin_face(reason)
            else:
                if bus.isConnected():
                    interface = QDBusInterface(
                        "org.facegate.FaceGate",
                        "/org/facegate/FaceGate",
                        "org.facegate.FaceGate",
                        bus
                    )
                    if interface.isValid():
                        raw_reply = interface.call("RequestAuth", reason)
                        reply = QDBusReply(raw_reply)
                        if reply.isValid():
                            success = reply.value()
                            if success:
                                from database.embedding_store import get_cached_key
                                if get_cached_key():
                                    logging.info("Encryption key loaded from RAM key file after daemon auth in SettingsWindow.")
                            return success
        except Exception as e:
            logging.error(f"Failed to verify settings action '{reason}' via D-Bus: {e}")
            
        # Fallback to local AuthDialog
        from database.embedding_store import EMBEDDING_FILE, OLD_EMBEDDING_FILE
        import os
        from ui.auth_dialog import AuthDialog
        mode = "face" if (os.path.exists(EMBEDDING_FILE) or os.path.exists(OLD_EMBEDDING_FILE)) else "password"
        dialog = AuthDialog(reason, mode=mode, parent=self)
        res = dialog.exec()
        return res == QDialog.DialogCode.Accepted

    def handle_protection_clicked(self, checked):
        # Disabling protection requires auth
        if not checked:
            logging.info("Request to disable App Deletion Protection. Requiring verification.")
            if not self.verify_settings_action("Disable Deletion Protection"):
                self.protection_check.setChecked(True)
                QMessageBox.warning(self, "Verification Failed", "Authentication failed. App Deletion Protection remains active.")
            else:
                logging.info("App Deletion Protection successfully disabled.")

    def trigger_password_change(self):
        dialog = ChangePasswordDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(self, "Success", "Master password updated successfully.")
        else:
            logging.info("Password change cancelled or failed.")

    # ------------------ Save Settings ------------------
    
    def save_and_close(self):
        # Only require verification if actual changes were made
        if self._has_pending_changes:
            if not self.verify_settings_action("Save Settings"):
                logging.info("Save settings cancelled due to verification failure.")
                return

        # 1. Update systemd login service configuration
        should_autostart = self.autostart_check.isChecked()
        current_autostart = is_enabled()
        
        if should_autostart != current_autostart:
            if should_autostart:
                enable()
            else:
                disable()
                
        # 2. Compare current_apps with initial_apps to apply substitutions
        initial_set = {app["id"]: app for app in self.initial_apps}
        current_set = {app["id"]: app for app in self.current_apps}
        
        # Apps removed: present in initial but not in current
        removed_apps = [app for app_id, app in initial_set.items() if app_id not in current_set]
        for app in removed_apps:
            try:
                restore_substitution([app])
                logging.info(f"Restored launcher for removed application: '{app['id']}'")
            except Exception as e:
                logging.error(f"Error restoring launcher for '{app['id']}': {e}")
                
        # Apps added: present in current but not in initial
        added_apps = [app for app_id, app in current_set.items() if app_id not in initial_set]
        if added_apps:
            try:
                apply_substitution(added_apps)
                logging.info(f"Applied substitutions for newly protected applications: {[a['id'] for a in added_apps]}")
            except Exception as e:
                logging.error(f"Error substituting launchers for added apps: {e}")

        selected_theme = self.theme_combo.itemData(self.theme_combo.currentIndex())
        self.config.set("behavior.theme", selected_theme)
        self.config.set("ui.theme", selected_theme)
        self.config.set("behavior.launch_at_login", should_autostart)
        self.config.set("behavior.uninstall_protection", self.protection_check.isChecked())
        self.config.set("app_monitor.on_auth_failure", self.policy_combo.itemData(self.policy_combo.currentIndex()))
        self.config.set("app_monitor.auth_timeout_seconds", self.timeout_spin.value())
        self.config.set("behavior.notify_on_auth", self.notify_check.isChecked())
        self.config.set("behavior.autolock_on_idle", self.idle_check.isChecked())
        self.config.set("behavior.autolock_on_idle_minutes", self.idle_spin.value())
        self.config.set("behavior.startup_delay_seconds", self.delay_spin.value())
        self.config.set("behavior.lock_on_sleep_or_lock", self.sleep_lock_check.isChecked())
        self.config.set("security.lock_settings_window", self.lock_settings_check.isChecked())
        
        # 4. Save and configure Emergency Kill hotkey in GSettings
        new_hotkey = self.hotkey_input.text().strip()
        old_hotkey = self.config.get("behavior.emergency_key", "<Control><Alt>k")
        if new_hotkey != old_hotkey:
            from utils.hotkey_manager import register_gnome_hotkey, unregister_gnome_hotkey
            if new_hotkey:
                register_gnome_hotkey(new_hotkey)
            else:
                unregister_gnome_hotkey()
            self.config.set("behavior.emergency_key", new_hotkey)

        # 4b. Save and configure Panic Lockdown hotkey in GSettings
        new_panic = self.panic_hotkey_input.text().strip()
        old_panic = self.config.get("behavior.panic_key", "<Control><Alt>l")
        if new_panic != old_panic:
            from utils.hotkey_manager import register_lock_hotkey, unregister_lock_hotkey
            if new_panic:
                register_lock_hotkey(new_panic)
            else:
                unregister_lock_hotkey()
            self.config.set("behavior.panic_key", new_panic)
        
        # Save updated protected apps
        self.config.set("protected_apps", self.current_apps)
        
        # Write config back to file
        if self.config.save():
            from database.embedding_store import notify_daemon_reload
            notify_daemon_reload()

            from ui.theme import get_colors
            c = get_colors()
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Settings Saved")
            msg_box.setText("Settings have been saved and applied immediately in real-time!")
            msg_box.setIcon(QMessageBox.Icon.Information)
            
            ok_btn = msg_box.addButton(QMessageBox.StandardButton.Ok)
            ok_btn.setStyleSheet(f"background-color: {c['ACCENT_PURPLE']}; color: white; padding: 6px 20px; min-width: 80px; font-weight: bold; border-radius: 6px; border: none;")
            
            msg_box.exec()
            self.accept()
        else:
            QMessageBox.critical(self, "Save Failed", "Failed to save configuration parameters.")

    def create_intruder_gallery_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QLabel("Intruder Alerts & Captures")
        from ui.theme import style_heading
        style_heading(header, 20)
        header.setProperty("heading_size", 20)
        self._themed_labels.append((header, "TEXT_PRIMARY"))
        layout.addWidget(header)

        desc = QLabel("View photos of unauthorized access attempts caught by the camera.")
        desc.setStyleSheet("font-size: 13px;")
        desc.setProperty("secondary", True)
        layout.addWidget(desc)

        # Clear All Button
        self.clear_intruders_btn = QPushButton("Clear All Photos")
        self.clear_intruders_btn.clicked.connect(self.clear_all_intruders)
        self.clear_intruders_btn.setObjectName("clearIntrudersBtn")
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.clear_intruders_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Scroll area for grid of captures
        from PySide6.QtWidgets import QScrollArea, QGridLayout, QFrame
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea, QScrollArea > QWidget, QAbstractScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#qt_scrollarea_viewport {
                background: transparent;
                border: none;
            }
        """)
        if self.scroll_area.viewport():
            self.scroll_area.viewport().setStyleSheet("background: transparent; border: none;")
        
        self.gallery_widget = QWidget()
        self.gallery_widget.setStyleSheet("background: transparent; border: none;")
        self.gallery_layout = QGridLayout(self.gallery_widget)
        self.gallery_layout.setSpacing(16)
        self.gallery_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area.setWidget(self.gallery_widget)
        layout.addWidget(self.scroll_area)

        # Empty State
        self.intruders_empty_label = QLabel("🛡️ No intruder attempts detected. Your system is safe!")
        self.intruders_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.intruders_empty_label.setStyleSheet("font-size: 15px; font-weight: bold; padding: 60px;")
        self.intruders_empty_label.setProperty("secondary", True)
        layout.addWidget(self.intruders_empty_label)

        self.tab_stack.addWidget(page)

    def populate_intruder_gallery(self):
        import glob
        import datetime
        from PySide6.QtGui import QPixmap
        
        # Remove old intruder labels from _themed_labels to prevent memory accumulation
        self._themed_labels = [(lbl, key) for (lbl, key) in self._themed_labels if not (hasattr(lbl, 'objectName') and lbl.objectName().startswith('intruder_'))]

        # Clear existing layout items
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        intruder_dir = os.path.expanduser("~/.config/facegate/intruders")
        if not os.path.exists(intruder_dir):
            files = []
        else:
            files = glob.glob(os.path.join(intruder_dir, "*.jpg"))
            files.sort(reverse=True) # Show newest first

        if not files:
            self.scroll_area.hide()
            self.clear_intruders_btn.hide()
            self.intruders_empty_label.show()
            return

        self.intruders_empty_label.hide()
        self.scroll_area.show()
        self.clear_intruders_btn.show()

        from ui.theme import get_colors, style_themed_label
        _c_colors = get_colors()
        app_text_color = _c_colors["TEXT_PRIMARY"]
        sec_text_color = _c_colors["TEXT_SECONDARY"]

        columns = 3
        from PySide6.QtWidgets import QFrame
        for index, filepath in enumerate(files):
            filename = os.path.basename(filepath)
            parts = filename.replace(".jpg", "").split("_")
            if len(parts) >= 3:
                date_str = parts[0]
                time_str = parts[1]
                app_name = "_".join(parts[2:])
                
                try:
                    dt = datetime.datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                    formatted_time = dt.strftime("%b %d, %Y - %I:%M:%S %p")
                except ValueError:
                    formatted_time = f"{date_str} {time_str}"
            else:
                app_name = filename
                formatted_time = "Unknown time"

            # Create a card for each capture
            card = QFrame()
            card.setObjectName("intruderCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(6)

            # Image label
            img_lbl = QLabel()
            img_lbl.setObjectName("intruderImg")
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                img_lbl.setPixmap(pixmap.scaled(180, 135, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
                img_lbl.setFixedSize(180, 135)
            else:
                img_lbl.setText("Image missing")
                img_lbl.setFixedSize(180, 135)
            card_layout.addWidget(img_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

            # App Name Label
            app_lbl = QLabel(f"<b>Attempted:</b> {app_name}")
            app_lbl.setObjectName("intruder_app_lbl")
            style_themed_label(app_lbl, "TEXT_PRIMARY", f"font-size: 12px; color: {app_text_color}; border: none; background: transparent;")
            app_lbl.setWordWrap(True)
            self._themed_labels.append((app_lbl, "TEXT_PRIMARY"))
            card_layout.addWidget(app_lbl)

            # Time Label
            time_lbl = QLabel(formatted_time)
            time_lbl.setObjectName("intruder_time_lbl")
            style_themed_label(time_lbl, "TEXT_SECONDARY", f"font-size: 11px; color: {sec_text_color}; border: none; background: transparent;")
            time_lbl.setProperty("secondary", True)
            self._themed_labels.append((time_lbl, "TEXT_SECONDARY"))
            card_layout.addWidget(time_lbl)

            # Delete Button
            del_btn = QPushButton("Delete")
            del_btn.setObjectName("deleteIntruderBtn")
            del_btn.clicked.connect(self.make_delete_intruder_callback(filepath))
            card_layout.addWidget(del_btn)

            row = index // columns
            col = index % columns
            self.gallery_layout.addWidget(card, row, col)

    def make_delete_intruder_callback(self, filepath):
        return lambda: self.delete_intruder_file(filepath)

    def delete_intruder_file(self, filepath):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            self.populate_intruder_gallery()
        except Exception as e:
            logging.error(f"Failed to delete intruder file: {e}")

    def clear_all_intruders(self):
        from ui.theme import get_colors
        c = get_colors()
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Clear All Photos")
        msg_box.setText("Are you sure you want to delete all caught intruder photos?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        yes_btn = msg_box.addButton(QMessageBox.StandardButton.Yes)
        no_btn = msg_box.addButton(QMessageBox.StandardButton.No)
        
        yes_btn.setStyleSheet("background-color: #ef4444; color: white; padding: 6px 16px; min-width: 80px; font-weight: bold; border-radius: 6px; border: none;")
        no_btn.setStyleSheet(f"background-color: {c['CANCEL_BTN_BG']}; color: {c['TEXT_PRIMARY']}; border: 1px solid {c['BORDER_NEUTRAL']}; padding: 6px 16px; min-width: 80px; font-weight: bold; border-radius: 6px;")
        
        msg_box.exec()
        if msg_box.clickedButton() == yes_btn:
            import glob
            intruder_dir = os.path.expanduser("~/.config/facegate/intruders")
            if os.path.exists(intruder_dir):
                for f in glob.glob(os.path.join(intruder_dir, "*.jpg")):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
            self.populate_intruder_gallery()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMaximized():
                self.window_layout.setContentsMargins(0, 0, 0, 0)
                from ui.theme import get_colors
                c = get_colors()
                self.main_container.setStyleSheet(f"""
                    QWidget#mainContainer {{
                        background-color: {c["BG_NEUTRAL"]};
                        border: none;
                        border-radius: 0px;
                    }}
                """)
                if hasattr(self, "shadow") and self.shadow is not None:
                    self.shadow.setEnabled(False)
            else:
                self.window_layout.setContentsMargins(0, 0, 0, 0)
                from ui.theme import get_colors
                c = get_colors()
                self.main_container.setStyleSheet(f"""
                    QWidget#mainContainer {{
                        background-color: {c["BG_NEUTRAL"]};
                        border: 1px solid {c["BORDER_NEUTRAL"]};
                        border-radius: 12px;
                    }}
                """)
                if hasattr(self, "shadow") and self.shadow is not None:
                    self.shadow.setEnabled(True)
        super().changeEvent(event)

    def apply_theme_dynamically(self):
        from ui.theme import get_theme_qss, get_sidebar_qss, get_colors
        c = get_colors()
        self.setStyleSheet(get_theme_qss() + get_sidebar_qss(c))
        
        # Sync the sliding theme toggle position
        if hasattr(self, "title_bar") and self.title_bar:
            self.title_bar.apply_theme_dynamically()
            if hasattr(self.title_bar, "theme_toggle"):
                self.title_bar.theme_toggle.update_toggle_state()
        
        # Refresh restart banner colors
        if hasattr(self, "restart_banner"):
            _banner_bg = "#2d261e" if c.get("IS_DARK") else "#fffbeb"
            _banner_text = "#fef3c7" if c.get("IS_DARK") else "#92400e"
            self.restart_banner.setStyleSheet(f"""
                QFrame#restartBanner {{
                    background-color: {_banner_bg};
                    border: 1px solid #d97706;
                    border-radius: 6px;
                }}
                QLabel {{
                    color: {_banner_text};
                    font-size: 13px;
                    border: none;
                }}
                QPushButton {{
                    background-color: #d97706;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: #b45309;
                }}
            """)
            
        # Apply current state borders
        if self.isMaximized():
            self.main_container.setStyleSheet(f"""
                QWidget#mainContainer {{
                    background-color: {c["BG_NEUTRAL"]};
                    border: none;
                    border-radius: 0px;
                }}
            """)
        else:
            self.main_container.setStyleSheet(f"""
                QWidget#mainContainer {{
                    background-color: {c["BG_NEUTRAL"]};
                    border: 1px solid {c["BORDER_NEUTRAL"]};
                    border-radius: 12px;
                }}
            """)

        # Refresh dynamic themed labels
        from ui.theme import style_heading, style_themed_label, get_card_qss
        for label, color_key in self._themed_labels:
            try:
                heading_size = label.property("heading_size")
                extra_css = label.property("extra_css") or ""
                if heading_size is not None:
                    style_heading(label, heading_size)
                else:
                    style_themed_label(label, color_key, extra_css)
            except Exception as e:
                logging.error(f"Error updating themed label color: {e}")

        # Re-theme all card widgets
        for card_ref, importance in [
            ("card_master_pwd", "accent"),
            ("card_enrolled", "accent"),
            ("card_security_profiles", "normal"),
            ("card_startup", "normal"),
            ("card_policy", "normal"),
            ("card_protection", "danger"),
            ("card_notifications", "normal"),
            ("card_about", "normal"),
        ]:
            card = getattr(self, card_ref, None)
            if card is not None:
                card.setStyleSheet(get_card_qss(importance, c))

        # Refresh enrolled users list colors
        if hasattr(self, "enrolled_users_container"):
            self.populate_enrolled_users()

        # Re-theme scrollbars for all scroll areas
        _scrollbar_bg = "#4c3d99" if c.get("IS_DARK") else "#c7d2fe"
        _scrollbar_hover = "#7c6ecf" if c.get("IS_DARK") else "#818cf8"
        for scroll in getattr(self, "_scroll_areas", []):
            try:
                scroll.setStyleSheet(f"""
                    QScrollArea {{
                        background: transparent;
                        border: none;
                    }}
                    QScrollBar:vertical {{
                        border: none;
                        background: transparent;
                        width: 8px;
                        margin: 0px 4px 0px 0px;
                    }}
                    QScrollBar::handle:vertical {{
                        background: {_scrollbar_bg};
                        border-radius: 4px;
                        min-height: 20px;
                    }}
                    QScrollBar::handle:vertical:hover {{
                        background: {_scrollbar_hover};
                    }}
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                        border: none;
                        background: none;
                    }}
                    QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                        border: none;
                        background: none;
                    }}
                """)
            except Exception as e:
                logging.error(f"Error updating scrollbar style: {e}")