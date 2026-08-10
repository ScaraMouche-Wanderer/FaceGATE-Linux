import logging
import ctypes
import time
import math
import numpy as np

# Preload libc and librt with RTLD_GLOBAL to resolve GLIBC symbol conflicts (__pointer_chk_guard) on Linux
try:
    ctypes.CDLL("libc.so.6", mode=ctypes.RTLD_GLOBAL)
except Exception:
    pass
try:
    ctypes.CDLL("librt.so.1", mode=ctypes.RTLD_GLOBAL)
except Exception:
    pass

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

def draw_tech_corner_reticle(img, bbox, color, text=""):
    """
    Draws sleek tech corner brackets and an animated vertical laser scan line.
    """
    import cv2
    x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    c_len = min(22, max(8, int(min(w, h) * 0.22)))
    thickness = 2
    
    # 4 Corner brackets
    # Top-Left
    cv2.line(img, (x1, y1), (x1 + c_len, y1), color, thickness)
    cv2.line(img, (x1, y1), (x1, y1 + c_len), color, thickness)
    # Top-Right
    cv2.line(img, (x2, y1), (x2 - c_len, y1), color, thickness)
    cv2.line(img, (x2, y1), (x2, y1 + c_len), color, thickness)
    # Bottom-Left
    cv2.line(img, (x1, y2), (x1 + c_len, y2), color, thickness)
    cv2.line(img, (x1, y2), (x1, y2 - c_len), color, thickness)
    # Bottom-Right
    cv2.line(img, (x2, y2), (x2 - c_len, y2), color, thickness)
    cv2.line(img, (x2, y2), (x2, y2 - c_len), color, thickness)

    # Animated laser scan line sweeping vertically over the face
    sweep_phase = (math.sin(time.time() * 3.0) + 1.0) / 2.0
    scan_y = int(y1 + sweep_phase * h)
    scan_y = max(y1, min(y2, scan_y))
    cv2.line(img, (x1 + 2, scan_y), (x2 - 2, scan_y), color, 1, cv2.LINE_AA)

    # Label text with clean background pill
    if text:
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        lbl_y1 = max(0, y1 - 22)
        lbl_y2 = max(text_h + 4, y1 - 4)
        cv2.rectangle(img, (x1, lbl_y1), (x1 + text_w + 10, lbl_y2), (20, 20, 30), cv2.FILLED)
        cv2.putText(img, text, (x1 + 5, lbl_y2 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

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
    def __init__(self, app_name: str, mode: str = "password", timeout_seconds: int = 0, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        
        # Determine theme mode from config (Light theme is always enforced for face mode to illuminate face)
        from utils.config_loader import get_config
        try:
            _cfg_theme = get_config().get("behavior.theme", "light")
            if _cfg_theme == "dark" and self.mode != "face":
                self.theme_mode = "dark"
            else:
                self.theme_mode = "light"
        except Exception:
            self.theme_mode = "light"
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
        self.warmup_frames_left = 3
        
        self.detector = None
        self.camera_worker = None
        
        self.grace_period_ms = int(get_config().get("authentication.password_fallback_grace_seconds", 15)) * 1000
        
        self.init_ui()
        
        # Show fallback button only after grace period, or immediately if key is not cached
        from database.embedding_store import get_cached_key
        if get_cached_key() is None:
            self.pwd_fallback_btn.setVisible(True)
        else:
            QTimer.singleShot(self.grace_period_ms, lambda: self.pwd_fallback_btn.setVisible(True))

    def init_ui(self):
        self.setWindowTitle("FaceGate Authentication")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        
        # Determine screen-based size & center on cursor screen
        from PySide6.QtGui import QGuiApplication, QCursor
        target_screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if target_screen:
            geom = target_screen.availableGeometry()
            if self.mode == "face":
                width = max(420, min(int(geom.width() * 0.35), 600))
                height = max(480, min(int(geom.height() * 0.55), 700))
                self.resize(width, height)
                self.setMinimumSize(400, 420)
            else:
                width = max(380, min(int(geom.width() * 0.3), 500))
                height = max(260, min(int(geom.height() * 0.35), 350))
                self.resize(width, height)
                self.setMinimumSize(360, 265)
            self.move(
                geom.x() + (geom.width() - self.width()) // 2,
                geom.y() + (geom.height() - self.height()) // 2
            )
        else:
            if self.mode == "face":
                self.resize(440, 500)
                self.setMinimumSize(400, 420)
            else:
                self.resize(400, 290)
                self.setMinimumSize(360, 265)
        
        from ui.theme import get_theme_qss, get_colors, CustomTitleBar
        c = get_colors(self.theme_mode)
        self.setStyleSheet(get_theme_qss(self.theme_mode) + f"""
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
                border-radius: 14px;
            }}
        """)
        from ui.theme import WindowDragResizeFilter
        self.drag_filter = WindowDragResizeFilter(self)
        
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
        self.status_label.setStyleSheet(f"font-size: 13px; color: {c['TEXT_SECONDARY']};")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        face_layout.addWidget(self.status_label)

        # Camera View QLabel
        self.camera_label = QLabel()
        self.camera_label.setFixedSize(360, 270)
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setStyleSheet(f"border: 2px solid {c['BORDER_NEUTRAL']}; border-radius: 8px; background-color: {c['CARD_NEUTRAL']};")
        face_layout.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Password Fallback Button
        self.pwd_fallback_btn = QPushButton("Use Password Instead")
        self.pwd_fallback_btn.setObjectName("pwdFallbackBtn")
        self.pwd_fallback_btn.clicked.connect(self.switch_to_password_mode)
        self.pwd_fallback_btn.setVisible(False)
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
                background-color: {c["DANGER_RED"]};
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

        # Setup lockout check on initialization (per app_name)
        self.lockout_timer = QTimer(self)
        self.lockout_timer.timeout.connect(self.update_lockout_countdown)
        self.lockout_seconds_remaining = 0
        
        from security.lockout_manager import is_locked_out
        is_locked, remaining = is_locked_out(self.app_name)
        if is_locked and remaining > 0:
            QTimer.singleShot(50, lambda: self.start_lockout(remaining))

        # Setup timeout timer if specified
        if self.timeout_seconds > 0:
            self.timeout_timer = QTimer(self)
            self.timeout_timer.setSingleShot(True)
            self.timeout_timer.timeout.connect(self.handle_timeout)
            
        self.apply_theme_dynamically()

    def apply_theme_dynamically(self):
        from ui.theme import get_theme_qss, get_colors
        c = get_colors(self.theme_mode)
        self.setStyleSheet(get_theme_qss(self.theme_mode) + f"""
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
        
        if hasattr(self, "camera_label") and self.camera_label:
            self.camera_label.setStyleSheet(f"border: 2px solid {c['BORDER_NEUTRAL']}; border-radius: 8px; background-color: {c['CARD_NEUTRAL']};")

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
            
            from database.embedding_store import load_embeddings, get_cached_key, EMBEDDING_FILE
            import os
            try:
                self.enrolled_embeddings = load_embeddings()
            except Exception as e:
                logging.error(f"Error loading enrolled embeddings: {e}")
                self.enrolled_embeddings = {}
                
            if not self.enrolled_embeddings:
                if get_cached_key() is None and os.path.exists(EMBEDDING_FILE):
                    logging.info("Vault is locked (no encryption key in RAM). Switching AuthDialog to password mode to prompt for master password.")
                    if hasattr(self, "sub_label") and self.sub_label:
                        self.sub_label.setText("🔒 Enter Master Password once to unlock Face Recognition for this session:")
                    self.switch_to_password_mode()
                    return
                elif get_cached_key() is not None:
                    logging.warning("No enrolled embeddings found in database. Switching to password mode.")
                    if hasattr(self, "sub_label") and self.sub_label:
                        self.sub_label.setText("No facial profiles enrolled yet. Enter master password:")
                    self.switch_to_password_mode()
                    return
                
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

        # Check for dark frame (e.g. physical camera privacy shutter closed or dim lighting)
        from ui.theme import get_colors
        c = get_colors(self.theme_mode)
        if frame is not None and frame.mean() < 15.0:
            self.status_label.setText("⚠️ Camera is dark — open camera cover or turn on light")
            self.status_label.setStyleSheet(f"color: {c['WARNING_AMBER']}; font-size: 13px; font-weight: bold;")
        else:
            self.status_label.setText("Position your face in the camera view...")
            self.status_label.setStyleSheet(f"font-size: 13px; color: {c['TEXT_SECONDARY']};")

        # 1. Update camera preview in GUI immediately (buttery-smooth 30 FPS)
        pixmap = convert_cv_to_pixmap(frame, 360, 270)
        self.camera_label.setPixmap(pixmap)

        # 2. Submit frame to background face detection thread
        if hasattr(self, "detector_worker") and self.detector_worker:
            self.detector_worker.submit_frame(frame)

    @Slot(list, object)
    def handle_detection_result(self, faces, frame):
        import cv2
        from ui.theme import get_colors
        from recognition.blur_checker import is_blurry
        c = get_colors()

        # Camera warmup: skip initial frames after startup to let camera auto-exposure stabilize
        if getattr(self, "warmup_frames_left", 0) > 0:
            self.warmup_frames_left -= 1
            return

        # Skip detection evaluation on severely blurry frames to prevent false matches (audit §6.5)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if is_blurry(gray, threshold=8.0):
            logging.debug("Skipping severely blurry camera frame during face recognition.")
            return
        
        # Save camera frame to latest_frame. If a face is found, we always update it.
        # Otherwise, if no frame has been captured yet, save this frame as a fallback.
        if len(faces) > 0 or not hasattr(self, "latest_frame") or self.latest_frame is None:
            self.latest_frame = frame.copy()
            
        display_frame = frame.copy()
        matched_user = None
        matched_score = 0.0
        matched_face = None
        
        from recognition.matcher import match_multi_faces
        face_matches = match_multi_faces(faces, self.enrolled_embeddings)
        
        for face, name, score in face_matches:
            bbox = face['bbox']
            if name:
                color = (0, 255, 0) # Green in BGR for recognized enrolled user
                text = f"{name} ({score:.2f})"
                if matched_user is None or score > matched_score:
                    matched_user = name
                    matched_score = score
                    matched_face = face
            else:
                color = (0, 0, 255) # Red in BGR for unknown bystander
                text = "Unknown"
                if score > 0:
                    text += f" ({score:.2f})"
            
            # Draw sleek reticle bounding box and label for every face in the camera frame
            draw_tech_corner_reticle(display_frame, bbox, color, text)

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
            
            from utils.config_loader import get_config
            config = get_config()
            threshold = float(config.get("recognition.similarity_threshold", 0.52))
            
            # High-confidence match (score >= threshold + 0.12) authenticates immediately
            if self.success_count >= 2 or matched_score >= (threshold + 0.12):
                # Fail-safe default: liveness/anti-spoofing is ON unless the operator
                # *explicitly* opts out with a negative value. A missing key, a zero,
                # or a malformed config value must never silently disable this check -
                # that would allow a static photo/screen to authenticate. See SECURITY.md
                # "Liveness Verification (Anti-Spoofing)".
                _SAFE_MIN_MOTION_FLOOR = 0.5
                raw_min_motion = config.get("recognition.liveness_min_motion", _SAFE_MIN_MOTION_FLOOR)
                try:
                    min_motion = float(raw_min_motion)
                except (TypeError, ValueError):
                    min_motion = _SAFE_MIN_MOTION_FLOOR
                if min_motion == 0.0:
                    min_motion = _SAFE_MIN_MOTION_FLOOR
                liveness_disabled = min_motion < 0.0
                if liveness_disabled:
                    logging.warning(
                        "Liveness/anti-spoofing check is explicitly DISABLED via config "
                        "(recognition.liveness_min_motion < 0). Static photo/screen "
                        "presentation attacks are not mitigated while this is set."
                    )

                total_dist = 0.0
                if len(self.matched_centroids) >= 2:
                    import math
                    for idx in range(1, len(self.matched_centroids)):
                        c1 = self.matched_centroids[idx - 1]
                        c2 = self.matched_centroids[idx]
                        total_dist += math.hypot(c2[0] - c1[0], c2[1] - c1[1])
                
                # Check liveness micro-motion unless explicitly disabled
                # Check liveness micro-motion and passive texture check unless explicitly disabled
                texture_passed = True
                texture_reason = ""
                if not liveness_disabled and matched_face:
                    from recognition.liveness import check_texture_liveness
                    x1, y1, x2, y2 = [int(v) for v in matched_face['bbox']]
                    h, w, _ = frame.shape
                    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
                    if x2 > x1 and y2 > y1:
                        crop = frame[y1:y2, x1:x2]
                        texture_passed, tex_score, texture_reason = check_texture_liveness(crop)

                if not liveness_disabled and total_dist < min_motion:
                    logging.info(f"Liveness motion check waiting: total motion {total_dist:.4f} < threshold {min_motion}")
                    self.status_label.setText("Verifying... slight movement recommended")
                elif not liveness_disabled and not texture_passed:
                    logging.warning(f"Passive texture liveness failed: {texture_reason}")
                    self.status_label.setText("Verifying... adjust position / lighting")
                else:
                    logging.info(f"Subprocess Auth: Matched enrolled user '{matched_user}' (Similarity: {matched_score:.4f}, Motion: {total_dist:.4f})")
                    self.final_score = matched_score
                    self.matched_user = matched_user
                    if self.mode == "face+password":
                        logging.info("2FA Dual-Factor Auth: Face matched! Prompting for master password step.")
                        self.face_verified = True
                        if hasattr(self, "sub_label") and self.sub_label:
                            self.sub_label.setText(f"👤 Face Verified ({matched_user})! Enter Master Password for 2FA:")
                        self.switch_to_password_mode()
                    else:
                        self.authenticated = True
                        self._show_success_overlay()
            else:
                self.status_label.setText("Verifying face match…")
                self.status_label.setStyleSheet(f"font-size: 13px; color: {c['TEXT_SECONDARY']};")
        else:
            if self.success_count > 0:
                self.success_count -= 1
            else:
                self.matched_centroids.clear()
            if len(faces) > 0:
                self.unknown_face_ticks += 1
                if not self.enrolled_embeddings:
                    self.status_label.setText("Scanning face... Click 'Use Password Instead' if needed.")
                    self.status_label.setStyleSheet(f"font-size: 13px; color: {c['TEXT_SECONDARY']};")
                if self.unknown_face_ticks >= 90: # ~3 seconds of continuous face scanning
                    logging.info("Face recognition scan complete. Recording biometric attempt & falling back to password.")
                    from security.lockout_manager import record_failed_attempt
                    record_failed_attempt(self.app_name)
                    self.switch_to_password_mode()
                    return

                # Find maximum score among detected faces to check for close mismatches
                max_score = 0.0
                for face, name, score in face_matches:
                    if score > max_score:
                        max_score = score
                        
                from utils.config_loader import get_config
                config = get_config()
                threshold = float(config.get("recognition.similarity_threshold", 0.52))
                margin = float(config.get("recognition.ambiguity_margin", 0.03))
                
                if max_score >= (threshold - margin):
                    self.status_label.setText("Almost — try better lighting or move closer")
                    self.status_label.setStyleSheet(f"color: {c['WARNING_AMBER']}; font-size: 13px; font-weight: bold;")
                    self.close_match_attempts += 1
                    if self.close_match_attempts >= 3:
                        logging.info("Too many close mismatch attempts. Recording biometric attempt & falling back to password.")
                        from security.lockout_manager import record_failed_attempt
                        record_failed_attempt(self.app_name)
                        self.switch_to_password_mode()
                else:
                    self.status_label.setText("Position your face in the camera view...")
                    self.status_label.setStyleSheet(f"font-size: 13px; color: {c['TEXT_SECONDARY']};")

    @Slot(str)
    def handle_camera_error(self, err_msg: str):
        self.camera_error = True
        self.camera_error_msg = err_msg
        self.cleanup_camera()
        from ui.theme import get_colors
        c = get_colors()
        self.status_label.setStyleSheet(f"color: {c['DANGER_RED']}; font-size: 13px; font-weight: bold;")
        self.status_label.setText(f"❌ Camera Error: {err_msg}")
        QTimer.singleShot(1000, self.switch_to_password_mode)

    def switch_to_password_mode(self):
        self.fallback_to_password = True
        self.cleanup_camera()
        
        # Adjust dialog size
        self.setMinimumSize(360, 265)
        self.resize(400, 290)
        self.stack.setCurrentIndex(1)
        self.raise_()
        self.activateWindow()
        self.password_input.setFocus()

    def handle_password_fallback(self):
        self.switch_to_password_mode()

    def handle_timeout(self):
        logging.warning("Authentication dialog timed out.")
        self.timed_out = True
        self.reject()

    def handle_unlock(self):
        import time
        from security.lockout_manager import record_failed_attempt, reset_lockout
        password = self.password_input.text()
        
        if verify_password(password):
            reset_lockout(self.app_name)
            self.authenticated = True
            import getpass
            self.matched_user = getpass.getuser()
            
            # Print derived key to stdout so parent daemon process caches key in memory & RAM tmpfs
            import sys
            from database.embedding_store import get_cached_key
            key = get_cached_key()
            if key:
                print(key.hex())
                sys.stdout.flush()
                
            self._show_success_overlay()
        else:
            from ui.sound_effects import SoundManager
            SoundManager.play_failure()
            attempts, lockout_until, remaining = record_failed_attempt(self.app_name)
            self.failed_pwd_attempts += 1
            self.password_input.selectAll()
            
            # Temporary error styling
            from ui.theme import get_colors as _get_colors
            _c = _get_colors()
            err_bg = "#3b1c1c" if _c.get("IS_DARK") else "#fef2f2"
            self.password_input.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {err_bg};
                    border: 1px solid {_c['DANGER_RED']};
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: {_c['TEXT_PRIMARY']};
                    font-size: 13px;
                }}
            """)
            
            if remaining > 0:
                self.start_lockout(remaining)
            else:
                remaining_attempts = max(0, 3 - attempts)
                self.error_label.setText(f"⚠️ Incorrect password. Try again. ({remaining_attempts} attempts remaining)")
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

    def _show_success_overlay(self):
        """Shows animated green checkmark overlay before accepting dialog."""
        try:
            from ui.sound_effects import SoundManager
            SoundManager.play_success()
            # If running inside pytest unit test suite, accept immediately
            import os, sys
            if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
                self.cleanup_camera()
                super().accept()
                return

            from ui.auth_overlays import AuthSuccessOverlay
            # Stop camera to free resources while overlay plays
            self.cleanup_camera()
            overlay = AuthSuccessOverlay(self.main_container)
            overlay.show_and_dismiss(callback=lambda: super(AuthDialog, self).accept(), delay_ms=900)
        except Exception as e:
            logging.error(f"Auth overlay error: {e}")
            self.cleanup_camera()
            super().accept()

    def accept(self):
        self.cleanup_camera()
        super().accept()

    def closeEvent(self, event):
        self.cleanup_camera()
        super().closeEvent(event)
