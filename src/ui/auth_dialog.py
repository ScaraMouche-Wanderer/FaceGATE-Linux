import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget
)
from PySide6.QtCore import Qt, QTimer, Slot, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from security.credential_store import verify_password

class DetectorLoader(QThread):
    loaded = Signal(object)
    error = Signal(str)
    
    def run(self):
        try:
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            models_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "models"))
            
            from recognition.detector import Detector
            detector = Detector(root_dir=models_dir)
            self.loaded.emit(detector)
        except Exception as e:
            self.error.emit(str(e))

import threading
import time

class FaceDetectorWorker(QThread):
    detected = Signal(list, object)  # Emits (faces, frame)
    
    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.frame_to_process = None
        self.lock = threading.Lock()
        self.running = True
        
    def submit_frame(self, frame):
        with self.lock:
            self.frame_to_process = frame
            
    def run(self):
        last_process_time = 0.0
        while self.running:
            frame = None
            current_time = time.perf_counter()
            # Rate limit: only run detection at most once every 150ms
            if current_time - last_process_time >= 0.15:
                with self.lock:
                    if self.frame_to_process is not None:
                        frame = self.frame_to_process
                        self.frame_to_process = None
                        last_process_time = current_time
                    
            if frame is not None:
                try:
                    faces = self.detector.detect_faces(frame)
                    self.detected.emit(faces, frame)
                except Exception as e:
                    logging.error(f"Error in background face detection: {e}")
            else:
                time.sleep(0.01)
                
    def stop(self):
        self.running = False
        self.wait()

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
    return QPixmap.fromImage(q_img.copy())

class AuthDialog(QDialog):
    # Class-level variables to track failed attempts and lockout across dialog instances in a single session
    failed_attempts_count = 0
    lockout_until = 0.0

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
        self.close_match_attempts = 0
        self.latest_frame = None
        self.unknown_face_ticks = 0
        self.matched_centroids = []
        self.enrolled_embeddings = {}
        self.failed_pwd_attempts = 0
        
        self.detector = None
        self.camera_worker = None
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("FaceGate Authentication")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Dialog
        )
        self.setModal(True)
        
        # Determine screen-based size
        from PySide6.QtGui import QGuiApplication, QColor
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_size = screen.size()
            if self.mode == "face":
                width = max(420, min(int(screen_size.width() * 0.35), 600))
                height = max(480, min(int(screen_size.height() * 0.55), 700))
                self.resize(width, height)
                self.setMinimumSize(400, 420)
            else:
                width = max(380, min(int(screen_size.width() * 0.3), 500))
                height = max(260, min(int(screen_size.height() * 0.35), 350))
                self.resize(width, height)
                self.setMinimumSize(360, 265)
        else:
            if self.mode == "face":
                self.resize(440, 500)
                self.setMinimumSize(400, 420)
            else:
                self.resize(400, 290)
                self.setMinimumSize(360, 265)
        
        from ui.theme import get_theme_qss, get_colors, CustomTitleBar, TEXT_SECONDARY, DANGER_RED
        c = get_colors()
        self.setStyleSheet(get_theme_qss() + f"""
            QPushButton#pwdFallbackBtn {{
                background-color: transparent;
                color: {c["ACCENT_PURPLE"]};
                border: none;
                font-size: 13px;
                font-weight: bold;
                text-decoration: underline;
            }}
            QPushButton#pwdFallbackBtn:hover {{
                color: {c["ACCENT_PURPLE_HOVER"]};
            }}
        """)

        # Outer layout
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container
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
        
        window_layout.addWidget(self.main_container)
        
        # Inner layout
        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Custom Title Bar
        self.title_bar = CustomTitleBar(self, title="FaceGate Authentication", allow_maximize=False, allow_minimize=False)
        container_layout.addWidget(self.title_bar)

        # Stacked layout for pages
        from PySide6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()
        container_layout.addWidget(self.stack)

        # PAGE 0: Face Mode
        face_page = QWidget()
        face_layout = QVBoxLayout(face_page)
        face_layout.setContentsMargins(24, 24, 24, 24)
        face_layout.setSpacing(16)
        
        self.header_label_face = QLabel(f"🔒 <b>{self.app_name}</b> is locked.")
        self.header_label_face.setObjectName("headerLabel")
        self.header_label_face.setAlignment(Qt.AlignmentFlag.AlignCenter)
        face_layout.addWidget(self.header_label_face)

        self.status_label = QLabel("Loading face recognition models...")
        self.status_label.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        face_layout.addWidget(self.status_label)

        # Camera View QLabel
        self.camera_label = QLabel()
        self.camera_label.setFixedSize(360, 270)
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setStyleSheet("border: 2px solid #3a3a4a; border-radius: 8px; background-color: #0d0d11;")
        face_layout.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Password Fallback Button
        self.pwd_fallback_btn = QPushButton("Use Password Instead")
        self.pwd_fallback_btn.setObjectName("pwdFallbackBtn")
        self.pwd_fallback_btn.clicked.connect(self.switch_to_password_mode)
        self.pwd_fallback_btn.setVisible(True)
        face_layout.addWidget(self.pwd_fallback_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Cancel Button
        face_btn_layout = QHBoxLayout()
        self.face_cancel_btn = QPushButton("Cancel")
        self.face_cancel_btn.setObjectName("cancelBtn")
        self.face_cancel_btn.clicked.connect(self.reject)
        face_btn_layout.addWidget(self.face_cancel_btn)
        face_layout.addLayout(face_btn_layout)

        self.stack.addWidget(face_page)

        # PAGE 1: Password Mode
        pwd_page = QWidget()
        pwd_layout = QVBoxLayout(pwd_page)
        pwd_layout.setContentsMargins(24, 24, 24, 24)
        pwd_layout.setSpacing(16)

        self.header_label_pwd = QLabel(f"🔒 <b>{self.app_name}</b> is locked.")
        self.header_label_pwd.setObjectName("headerLabel")
        self.header_label_pwd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pwd_layout.addWidget(self.header_label_pwd)

        self.sub_label = QLabel("Enter password to unlock application:")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pwd_layout.addWidget(self.sub_label)

        # Password Input
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Password")
        self.password_input.returnPressed.connect(self.handle_unlock)
        pwd_layout.addWidget(self.password_input)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: bold;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pwd_layout.addWidget(self.error_label)

        # Lockout progress bar (initially hidden)
        from PySide6.QtWidgets import QProgressBar
        self.lockout_progress = QProgressBar()
        self.lockout_progress.setTextVisible(False)
        self.lockout_progress.setFixedHeight(6)
        
        self.lockout_progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {c["BORDER_NEUTRAL"]};
                border-radius: 3px;
                background-color: {c["CANCEL_BTN_BG"]};
                height: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {DANGER_RED};
                border-radius: 2px;
            }}
        """)
        self.lockout_progress.hide()
        pwd_layout.addWidget(self.lockout_progress)

        # Buttons
        pwd_btn_layout = QHBoxLayout()
        pwd_btn_layout.setSpacing(12)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.unlock_btn = QPushButton("Unlock")
        self.unlock_btn.setDefault(True)
        self.unlock_btn.clicked.connect(self.handle_unlock)

        pwd_btn_layout.addWidget(self.cancel_btn)
        pwd_btn_layout.addWidget(self.unlock_btn)
        pwd_layout.addLayout(pwd_btn_layout)

        self.stack.addWidget(pwd_page)

        # Setup initial stack page and trigger camera if face mode
        if self.mode == "face":
            self.stack.setCurrentIndex(0)
            self.activateWindow()
            QTimer.singleShot(100, self.start_camera_and_models)
        else:
            self.stack.setCurrentIndex(1)
            QTimer.singleShot(50, self.password_input.setFocus)

        # Setup lockout check on initialization
        self.lockout_timer = QTimer(self)
        self.lockout_timer.timeout.connect(self.update_lockout_countdown)
        self.lockout_seconds_remaining = 0
        
        import math
        import time
        if time.time() < AuthDialog.lockout_until:
            remaining = int(math.ceil(AuthDialog.lockout_until - time.time()))
            if remaining > 0:
                QTimer.singleShot(50, lambda: self.start_lockout(remaining))

        # Setup timeout timer if specified
        if self.timeout_seconds > 0:
            self.timeout_timer = QTimer(self)
            self.timeout_timer.setSingleShot(True)
            self.timeout_timer.timeout.connect(self.handle_timeout)
            
        self.apply_theme_dynamically()

    def apply_theme_dynamically(self):
        from ui.theme import get_theme_qss, get_colors
        c = get_colors()
        self.setStyleSheet(get_theme_qss() + f"""
            QLabel#headerLabel {{
                font-size: 16px;
                font-weight: 500;
                color: {c["TEXT_PRIMARY"]};
            }}
            QPushButton#pwdFallbackBtn {{
                background-color: transparent;
                color: {c["ACCENT_PURPLE"]};
                border: none;
                font-size: 13px;
                font-weight: bold;
                text-decoration: underline;
            }}
            QPushButton#pwdFallbackBtn:hover {{
                color: {c["ACCENT_PURPLE_HOVER"]};
            }}
        """)
        self.main_container.setStyleSheet(f"""
            QWidget#mainContainer {{
                background-color: {c["BG_NEUTRAL"]};
                border: 1px solid {c["BORDER_NEUTRAL"]};
                border-radius: 12px;
            }}
        """)
        
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setStyleSheet(f"font-size: 13px; color: {c['TEXT_SECONDARY']};")
        if hasattr(self, "sub_label") and self.sub_label:
            self.sub_label.setStyleSheet(f"font-size: 13px; color: {c['TEXT_SECONDARY']};")
            
        if hasattr(self, "lockout_progress") and self.lockout_progress:
            self.lockout_progress.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid {c["BORDER_NEUTRAL"]};
                    border-radius: 3px;
                    background-color: {c["CANCEL_BTN_BG"]};
                    height: 6px;
                }}
                QProgressBar::chunk {{
                    background-color: #ef4444;
                    border-radius: 2px;
                }}
            """)
            
        if hasattr(self, "title_bar") and self.title_bar:
            self.title_bar.apply_theme_dynamically()

    def start_camera_and_models(self):
        self.status_label.setText("Initializing face recognition detector...")
        self.loader = DetectorLoader(self)
        self.loader.loaded.connect(self.on_detector_loaded)
        self.loader.error.connect(self.on_detector_load_error)
        self.loader.start()

    def on_detector_loaded(self, detector):
        try:
            self.detector = detector
            
            from database.embedding_store import load_embeddings
            try:
                self.enrolled_embeddings = load_embeddings()
            except Exception as e:
                logging.error(f"Error loading enrolled embeddings: {e}")
                self.enrolled_embeddings = {}
                
            # Start background face detection worker
            self.detector_worker = FaceDetectorWorker(self.detector)
            self.detector_worker.detected.connect(self.handle_detection_result)
            self.detector_worker.start()
            
            from camera.camera_worker import CameraWorker
            self.camera_worker = CameraWorker()
            self.camera_worker.signals.frame_ready.connect(self.handle_frame, Qt.ConnectionType.QueuedConnection)
            self.camera_worker.signals.error.connect(self.handle_camera_error, Qt.ConnectionType.QueuedConnection)
            self.status_label.setText("Accessing video capture device...")
            
            # Start timeout timer now that models are loaded and camera starts
            if hasattr(self, "timeout_timer") and self.timeout_seconds > 0:
                self.timeout_timer.start(self.timeout_seconds * 1000)
                
            self.camera_worker.start()
        except Exception as e:
            logging.error(f"Error starting camera: {e}")
            self.handle_camera_error(str(e))

    def on_detector_load_error(self, err_msg):
        logging.error(f"Error starting face recognition: {err_msg}")
        self.handle_camera_error(err_msg)

    @Slot(object)
    def handle_frame(self, frame: "np.ndarray"):
        if self.detector is None:
            return
            
        self.status_label.setText("Position your face in the camera view...")
        
        # 1. Update camera preview in GUI immediately (buttery-smooth 30 FPS)
        pixmap = convert_cv_to_pixmap(frame, 360, 270)
        self.camera_label.setPixmap(pixmap)
        
        # 2. Submit frame to background face detection thread
        if hasattr(self, "detector_worker") and self.detector_worker:
            self.detector_worker.submit_frame(frame)

    @Slot(list, object)
    def handle_detection_result(self, faces, frame):
        import cv2
        from ui.theme import TEXT_SECONDARY, WARNING_AMBER
        
        # Save camera frame to latest_frame. If a face is found, we always update it.
        # Otherwise, if no frame has been captured yet, save this frame as a fallback.
        if len(faces) > 0 or not hasattr(self, "latest_frame") or self.latest_frame is None:
            self.latest_frame = frame.copy()
            
        display_frame = frame.copy()
        matched_user = None
        matched_score = 0.0
        matched_face = None
        
        face_matches = []
        for face in faces:
            bbox = face['bbox']
            emb = face['embedding']
            
            from recognition.matcher import match_face
            name, score = match_face(emb, self.enrolled_embeddings)
            face_matches.append((face, name, score))
            
            if name:
                color = (0, 255, 0) # Green in BGR
                text = f"{name} ({score:.2f})"
                matched_user = name
                matched_score = score
                matched_face = face
            else:
                color = (0, 0, 255) # Red in BGR
                text = f"Unknown"
                if score > 0:
                    text += f" ({score:.2f})"
            
            # Draw bounding box and label
            cv2.rectangle(display_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
            cv2.putText(display_frame, text, (bbox[0], bbox[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # Update preview with overlays
        pixmap = convert_cv_to_pixmap(display_frame, 360, 270)
        self.camera_label.setPixmap(pixmap)

        # Handle matching threshold
        if matched_user and matched_face:
            self.success_count += 1
            
            # Record centroid of matched face
            bbox = matched_face['bbox']
            centroid = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
            self.matched_centroids.append(centroid)
            
            if self.success_count >= 3:
                # Perform motion/liveness check
                from utils.config_loader import get_config
                config = get_config()
                min_motion = float(config.get("recognition.liveness_min_motion", 0.5))
                
                total_dist = 0.0
                if len(self.matched_centroids) >= 3:
                    import math
                    for idx in range(1, len(self.matched_centroids)):
                        c1 = self.matched_centroids[idx - 1]
                        c2 = self.matched_centroids[idx]
                        total_dist += math.hypot(c2[0] - c1[0], c2[1] - c1[1])
                
                if total_dist < min_motion:
                    logging.warning(f"Liveness check failed: total motion {total_dist:.4f} < threshold {min_motion}")
                    self.success_count = 0
                    self.matched_centroids.clear()
                    self.status_label.setText("Liveness verification failed. Retrying...")
                else:
                    logging.info(f"Subprocess Auth: Matched enrolled user '{matched_user}' (Similarity: {matched_score:.4f}, Liveness motion: {total_dist:.4f})")
                    self.authenticated = True
                    self.final_score = matched_score
                    self.matched_user = matched_user
                    self.accept()
            else:
                self.status_label.setText("Hold still, verifying liveness…")
                self.status_label.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        else:
            self.success_count = 0
            self.matched_centroids.clear()
            if len(faces) > 0:
                self.unknown_face_ticks += 1
                if self.unknown_face_ticks >= 45: # ~1.5 - 2s of unknown face detection
                    logging.info("Face recognition failed (unknown face threshold). Falling back to password.")
                    self.switch_to_password_mode()
                    return

                # Find maximum score among detected faces to check for close mismatches
                max_score = 0.0
                for face, name, score in face_matches:
                    if score > max_score:
                        max_score = score
                        
                from utils.config_loader import get_config
                config = get_config()
                threshold = float(config.get("recognition.similarity_threshold", 0.65))
                margin = float(config.get("recognition.ambiguity_margin", 0.03))
                
                if max_score >= (threshold - margin):
                    self.status_label.setText("Almost — try better lighting or move closer")
                    self.status_label.setStyleSheet(f"color: {WARNING_AMBER}; font-size: 13px; font-weight: bold;")
                    self.close_match_attempts += 1
                    if self.close_match_attempts >= 3:
                        logging.info("Too many close mismatch attempts. Falling back to password.")
                        self.switch_to_password_mode()
                else:
                    self.status_label.setText("Position your face in the camera view...")
                    self.status_label.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")

    @Slot(str)
    def handle_camera_error(self, err_msg: str):
        self.camera_error = True
        self.camera_error_msg = err_msg
        self.cleanup_camera()
        from ui.theme import DANGER_RED
        self.status_label.setStyleSheet(f"color: {DANGER_RED}; font-size: 13px; font-weight: bold;")
        self.status_label.setText(f"❌ Camera Error: {err_msg}")
        QTimer.singleShot(1000, self.switch_to_password_mode)

    def switch_to_password_mode(self):
        self.fallback_to_password = True
        self.cleanup_camera()
        
        # Adjust dialog size
        self.setMinimumSize(360, 265)
        self.resize(400, 290)
        self.stack.setCurrentIndex(1)
        self.password_input.setFocus()

    def handle_password_fallback(self):
        self.switch_to_password_mode()

    def handle_timeout(self):
        logging.warning("Authentication dialog timed out.")
        self.timed_out = True
        self.reject()

    def handle_unlock(self):
        import time
        password = self.password_input.text()
        if verify_password(password):
            AuthDialog.failed_attempts_count = 0
            AuthDialog.lockout_until = 0.0
            self.authenticated = True
            import getpass
            self.matched_user = getpass.getuser()
            self.accept()
        else:
            AuthDialog.failed_attempts_count += 1
            self.failed_pwd_attempts += 1
            self.password_input.selectAll()
            
            # Temporary error styling
            from ui.theme import DANGER_RED, get_colors as _get_colors
            _c = _get_colors()
            err_bg = "#3b1c1c" if _c.get("IS_DARK") else "#fef2f2"
            self.password_input.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {err_bg};
                    border: 1px solid {DANGER_RED};
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: {_c['TEXT_PRIMARY']};
                    font-size: 13px;
                }}
            """)
            
            if AuthDialog.failed_attempts_count >= 3:
                attempts = AuthDialog.failed_attempts_count
                if attempts == 3:
                    delay = 2
                elif attempts == 4:
                    delay = 5
                elif attempts == 5:
                    delay = 15
                else:
                    delay = 30
                    
                AuthDialog.lockout_until = time.time() + delay
                self.start_lockout(delay)
            else:
                self.error_label.setText(f"⚠️ Incorrect password. Try again. ({3 - AuthDialog.failed_attempts_count} attempts remaining)")
                QTimer.singleShot(1500, self.reset_input_style)

    def start_lockout(self, seconds):
        self.password_input.setEnabled(False)
        self.unlock_btn.setEnabled(False)
        self.error_label.setText(f"Too many failed attempts. Locked out for {seconds}s.")
        self.lockout_seconds_remaining = seconds
        
        # Configure progress bar
        self.lockout_progress.setRange(0, seconds * 10)
        self.lockout_progress.setValue(seconds * 10)
        self.lockout_progress.show()
        
        self.lockout_timer.start(100) # 100ms smooth updates

    def update_lockout_countdown(self):
        val = self.lockout_progress.value() - 1
        self.lockout_progress.setValue(val)
        
        secs_remaining = int(val / 10)
        
        if val <= 0:
            self.lockout_timer.stop()
            self.password_input.setEnabled(True)
            self.unlock_btn.setEnabled(True)
            self.error_label.setText("")
            self.lockout_progress.hide()
            self.password_input.setStyleSheet("") # Restore default stylesheet
        else:
            self.error_label.setText(f"Too many failed attempts. Locked out for {secs_remaining + 1}s.")

    def reset_input_style(self):
        if self.mode != "face":
            self.password_input.setStyleSheet("")

    def cleanup_camera(self):
        if self.camera_worker:
            try:
                self.camera_worker.signals.frame_ready.disconnect(self.handle_frame)
                self.camera_worker.signals.error.disconnect(self.handle_camera_error)
            except Exception:
                pass
            self.camera_worker.stop()
            self.camera_worker = None
            
        if hasattr(self, "detector_worker") and self.detector_worker:
            self.detector_worker.stop()
            self.detector_worker = None

    def reject(self):
        self.cleanup_camera()
        if not self.authenticated:
            if (self.timed_out or 
                self.close_match_attempts > 0 or 
                self.unknown_face_ticks > 0 or 
                self.failed_pwd_attempts > 0):
                self.save_intruder_selfie()
        super().reject()

    def save_intruder_selfie(self):
        if not hasattr(self, "latest_frame") or self.latest_frame is None:
            return
        try:
            import os
            import cv2
            import datetime
            
            intruder_dir = os.path.expanduser("~/.config/facegate/intruders")
            os.makedirs(intruder_dir, exist_ok=True)
            os.chmod(intruder_dir, 0o700)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_app_name = "".join(c for c in self.app_name if c.isalnum() or c in ("-", "_")).strip()
            if not safe_app_name:
                safe_app_name = "unknown"
                
            filename = f"{timestamp}_{safe_app_name}.jpg"
            filepath = os.path.join(intruder_dir, filename)
            
            cv2.imwrite(filepath, self.latest_frame)
            os.chmod(filepath, 0o600)
            logging.info(f"Intruder selfie captured and saved to: {filepath}")
        except Exception as e:
            logging.error(f"Failed to save intruder selfie: {e}")

    def accept(self):
        self.cleanup_camera()
        super().accept()

    def closeEvent(self, event):
        self.cleanup_camera()
        super().closeEvent(event)
