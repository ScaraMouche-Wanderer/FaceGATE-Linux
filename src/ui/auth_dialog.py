import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QApplication
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QImage, QPixmap
from security.credential_store import verify_password

def convert_cv_to_pixmap(frame: "np.ndarray", width: int = 360, height: int = 270) -> QPixmap:
    """
    Utility to convert an OpenCV BGR frame to a Qt QPixmap.
    """
    import cv2
    resized = cv2.resize(frame, (width, height))
    rgb_image = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(q_img)

class AuthDialog(QDialog):
    def __init__(self, app_name: str, mode: str = "password", timeout_seconds: int = 0, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        
        self.authenticated = False
        self.fallback_to_password = False
        self.camera_error = False
        self.timed_out = False
        self.success_count = 0
        self.final_score = None
        
        self.detector = None
        self.camera_worker = None
        
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
        
        if self.mode == "face":
            self.setFixedSize(420, 480)
        else:
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
            QPushButton#pwdFallbackBtn {
                background-color: transparent;
                color: #6366f1;
                border: none;
                font-size: 13px;
                font-weight: bold;
                text-decoration: underline;
            }
            QPushButton#pwdFallbackBtn:hover {
                color: #818cf8;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        if self.mode == "face":
            # Header Info
            header_label = QLabel(f"🔒 <b>{self.app_name}</b> is locked.")
            header_label.setStyleSheet("font-size: 16px; font-weight: 500;")
            header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(header_label)

            self.status_label = QLabel("Loading face recognition models...")
            self.status_label.setStyleSheet("font-size: 13px; color: #a0aec0;")
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.status_label)

            # Camera View QLabel
            self.camera_label = QLabel()
            self.camera_label.setFixedSize(360, 270)
            self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.camera_label.setStyleSheet("border: 2px solid #3a3a4a; border-radius: 8px; background-color: #0d0d11;")
            layout.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignCenter)

            # Password Fallback Button
            self.pwd_fallback_btn = QPushButton("Use Password Instead")
            self.pwd_fallback_btn.setObjectName("pwdFallbackBtn")
            self.pwd_fallback_btn.clicked.connect(self.handle_password_fallback)
            layout.addWidget(self.pwd_fallback_btn, alignment=Qt.AlignmentFlag.AlignCenter)

            # Cancel Button
            btn_layout = QHBoxLayout()
            self.cancel_btn = QPushButton("Cancel")
            self.cancel_btn.setObjectName("cancelBtn")
            self.cancel_btn.clicked.connect(self.reject)
            btn_layout.addWidget(self.cancel_btn)
            layout.addLayout(btn_layout)

            # Force window stays on top
            self.activateWindow()
            
            # Start Camera and Model load after window displays
            QTimer.singleShot(100, self.start_camera_and_models)

        else:
            # Password Mode (Phase 1 fallback)
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

            QTimer.singleShot(50, self.password_input.setFocus)

        self.setLayout(layout)

        # Setup timeout timer if specified
        if self.timeout_seconds > 0:
            self.timeout_timer = QTimer(self)
            self.timeout_timer.setSingleShot(True)
            self.timeout_timer.timeout.connect(self.handle_timeout)
            self.timeout_timer.start(self.timeout_seconds * 1000)

    def start_camera_and_models(self):
        try:
            self.status_label.setText("Initializing face recognition detector...")
            QApplication.processEvents()

            # Dynamic import of heavy libraries
            from recognition.detector import Detector
            from camera.camera_worker import CameraWorker

            self.detector = Detector()
            self.camera_worker = CameraWorker()
            
            self.camera_worker.signals.frame_ready.connect(self.handle_frame)
            self.camera_worker.signals.error.connect(self.handle_camera_error)
            
            self.status_label.setText("Accessing video capture device...")
            self.camera_worker.start()
        except Exception as e:
            logging.error(f"Error starting face recognition: {e}")
            self.handle_camera_error(str(e))

    @Slot(object)
    def handle_frame(self, frame: "np.ndarray"):
        import cv2
        if self.detector is None:
            return
            
        self.status_label.setText("Position your face in the camera view...")
        
        # 1. Detect faces in BGR frame
        faces = self.detector.detect_faces(frame)
        
        # 2. Draw overlays on BGR copy
        display_frame = frame.copy()
        matched_user = None
        matched_score = 0.0
        
        for face in faces:
            bbox = face['bbox']
            emb = face['embedding']
            
            from recognition.matcher import match_face
            name, score = match_face(emb)
            
            if name:
                color = (0, 255, 0) # Green in BGR
                text = f"{name} ({score:.2f})"
                matched_user = name
                matched_score = score
            else:
                color = (0, 0, 255) # Red in BGR
                text = f"Unknown"
                if score > 0:
                    text += f" ({score:.2f})"
            
            # Draw bounding box and label
            cv2.rectangle(display_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
            cv2.putText(display_frame, text, (bbox[0], bbox[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # 3. Update preview QLabel
        pixmap = convert_cv_to_pixmap(display_frame, 360, 270)
        self.camera_label.setPixmap(pixmap)

        # 4. Handle matching threshold
        if matched_user:
            self.success_count += 1
            # Require 3 consecutive frames of matching to authenticate securely
            if self.success_count >= 3:
                logging.info(f"Subprocess Auth: Matched enrolled user '{matched_user}' (Similarity: {matched_score:.4f})")
                self.authenticated = True
                self.final_score = matched_score
                self.accept()
        else:
            self.success_count = 0

    @Slot(str)
    def handle_camera_error(self, err_msg: str):
        self.camera_error = True
        self.reject()

    def handle_password_fallback(self):
        self.fallback_to_password = True
        self.reject()

    def handle_timeout(self):
        logging.warning("Authentication dialog timed out.")
        self.timed_out = True
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
            QTimer.singleShot(1500, self.reset_input_style)

    def reset_input_style(self):
        if self.mode != "face":
            self.password_input.setStyleSheet("")

    def cleanup_camera(self):
        if self.camera_worker:
            self.camera_worker.stop()
            self.camera_worker = None

    def reject(self):
        self.cleanup_camera()
        super().reject()

    def accept(self):
        self.cleanup_camera()
        super().accept()

    def closeEvent(self, event):
        self.cleanup_camera()
        super().closeEvent(event)
