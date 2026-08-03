import time
import logging
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QStackedWidget, QWidget, QMessageBox
)
from PySide6.QtCore import Qt, Slot
from camera.camera_worker import CameraWorker
from recognition.blur_checker import is_blurry
from database.embedding_store import save_embedding, load_embeddings, get_cached_key
from security.credential_store import verify_password
from ui.auth_dialog import convert_cv_to_pixmap, FaceDetectorWorker

class EnrollmentWizard(QDialog):
    def __init__(self, parent=None, target_username: str = ""):
        super().__init__(parent)
        self.target_username = target_username
        # Determine theme mode from config
        from utils.config_loader import get_config
        from ui.theme import is_system_dark_mode
        try:
            _cfg_theme = get_config().get("behavior.theme", "light")
            if _cfg_theme == "dark":
                self.theme_mode = "dark"
            else:
                self.theme_mode = "light"
        except Exception:
            self.theme_mode = "light"
        self.detector = None
        self.camera_worker = None
        
        self.username = target_username
        self.embeddings = []
        self.required_frames = 15
        self.processing_fps_limiter = 0.0 # Time threshold
        self.last_frame_processed_time = 0.0
        self.avg_embedding = None
        self.duplicate_user = None
        self.duplicate_similarity = 0.0
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("FaceGate Enrollment Wizard")
        self.setModal(True)

        # Determine screen-based size
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_size = screen.size()
            width = int(screen_size.width() * 0.35)
            height = int(screen_size.height() * 0.55)
            width = max(500, min(width, 700))
            height = max(520, min(height, 750))
            self.resize(width + 20, height + 20)
            self.setMinimumSize(480 + 20, 500 + 20)
        else:
            self.resize(520, 540)
            self.setMinimumSize(500, 520)

        # Apply global theme stylesheet
        from ui.theme import get_theme_qss, get_colors, CustomTitleBar
        c = get_colors(self.theme_mode)
        self.setStyleSheet(get_theme_qss(self.theme_mode))
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
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
        
        # Custom Title Bar (wizards don't resize or minimize)
        self.title_bar = CustomTitleBar(self, title="FaceGate Enrollment Wizard", allow_maximize=False, allow_minimize=False)
        container_layout.addWidget(self.title_bar)
        
        # Content layout widget
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        container_layout.addWidget(content_widget)
        
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # 1. Page 0: Intro & Username input & password validation if needed
        self.create_intro_page()
        
        # 2. Page 1: Capture with live camera and instructions
        self.create_capture_page()
        
        # 3. Page 2: Success review and confirm
        self.create_success_page()

        self.stack.setCurrentIndex(0)
        self.intro_next_btn.setDefault(True)
        self.apply_theme_dynamically()

    # ------------------ Page Creation ------------------
    
    def create_intro_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header_text = f"Re-Enroll User: {self.target_username}" if self.target_username else "Enrolled User Setup"
        header = QLabel(header_text)
        header.setObjectName("wizardHeader")
        layout.addWidget(header)

        desc_text = (
            f"Re-enrolling face profile for user '{self.target_username}'. Click Next to start camera capture."
            if self.target_username else
            "Welcome to the guided FaceGate user enrollment. Enter the username you want to associate with your facial profile."
        )
        desc = QLabel(desc_text)
        desc.setObjectName("wizardDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Username Input
        u_layout = QVBoxLayout()
        u_layout.setSpacing(6)
        u_lbl = QLabel("Enrolling Username:")
        u_lbl.setObjectName("boldLabel")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("e.g. voidnode")
        self.username_input.returnPressed.connect(self.process_intro_next)
        if self.target_username:
            self.username_input.setText(self.target_username)
            self.username_input.setReadOnly(True)
        u_layout.addWidget(u_lbl)
        u_layout.addWidget(self.username_input)
        layout.addLayout(u_layout)

        # Password validation if key not cached
        self.pwd_container = QWidget()
        pwd_layout = QVBoxLayout(self.pwd_container)
        pwd_layout.setContentsMargins(0, 0, 0, 0)
        pwd_layout.setSpacing(6)
        
        pwd_lbl = QLabel("Enter Master Password to Unlock Database:")
        pwd_lbl.setObjectName("warningLabel")
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.returnPressed.connect(self.process_intro_next)
        pwd_layout.addWidget(pwd_lbl)
        pwd_layout.addWidget(self.pwd_input)
        layout.addWidget(self.pwd_container)
        
        # Check if password field needs to be visible
        if get_cached_key() is not None:
            self.pwd_container.hide()

        layout.addStretch()

        # Navigation
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        
        self.intro_next_btn = QPushButton("Next")
        self.intro_next_btn.clicked.connect(self.process_intro_next)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.intro_next_btn)
        layout.addLayout(btn_layout)

        self.stack.addWidget(page)

    def create_capture_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.guided_lbl = QLabel("Face Guided Capture")
        self.guided_lbl.setObjectName("guidedHeader")
        layout.addWidget(self.guided_lbl)

        # Instructions
        self.instruction_lbl = QLabel("Starting camera...")
        self.instruction_lbl.setObjectName("instructionLabel")
        self.instruction_lbl.setWordWrap(True)
        self.instruction_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.instruction_lbl)

        from ui.theme import get_colors
        c_init = get_colors(self.theme_mode)
        # Video Frame box
        self.camera_label = QLabel()
        self.camera_label.setFixedSize(360, 270)
        self.camera_label.setStyleSheet(f"background-color: {c_init['CARD_NEUTRAL']}; border: 1px solid {c_init['BORDER_NEUTRAL']}; border-radius: 8px;")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, self.required_frames)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        # Stop button if user wants to cancel
        btn_layout = QHBoxLayout()
        self.capture_cancel_btn = QPushButton("Cancel Capture")
        self.capture_cancel_btn.setObjectName("cancelBtn")
        self.capture_cancel_btn.clicked.connect(self.cancel_capture_flow)
        btn_layout.addWidget(self.capture_cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.stack.addWidget(page)

    def create_success_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QLabel("Capture Succeeded!")
        header.setObjectName("successHeader")
        layout.addWidget(header)

        self.success_msg_lbl = QLabel()
        self.success_msg_lbl.setObjectName("wizardDesc")
        self.success_msg_lbl.setWordWrap(True)
        layout.addWidget(self.success_msg_lbl)

        layout.addStretch()

        # Finish buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Save Face Profile")
        self.save_btn.clicked.connect(self.save_enrollment)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

        self.stack.addWidget(page)

    # ------------------ Navigation Handlers ------------------
    
    def process_intro_next(self):
        username = self.username_input.text().strip()
        if not username:
            QMessageBox.warning(self, "Invalid Username", "Username cannot be empty.")
            return

        # Validate username format (security: prevent injection via special chars)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]{1,32}$', username):
            QMessageBox.warning(
                self, "Invalid Username",
                "Username must be 1-32 characters and contain only letters, numbers, underscores, and hyphens."
            )
            return

        # Handle password validation if key is not cached
        if get_cached_key() is None:
            password = self.pwd_input.text()
            if not password:
                QMessageBox.warning(self, "Password Required", "Master password is required to decrypt/update database.")
                return
            
            # Verify and cache key in memory
            if not verify_password(password):
                from database.embedding_store import EMBEDDING_FILE, OLD_EMBEDDING_FILE
                import os
                if not os.path.exists(EMBEDDING_FILE) and not os.path.exists(OLD_EMBEDDING_FILE):
                    if len(password) < 8:
                        QMessageBox.warning(self, "Password Too Short", "Master password must be at least 8 characters long.")
                        return
                    from security.credential_store import update_master_password
                    try:
                        update_master_password(None, password)
                        self.pwd_container.hide()
                    except Exception as ex:
                        QMessageBox.critical(self, "Setup Failed", f"Failed to initialize master password: {ex}")
                        return
                else:
                    QMessageBox.critical(self, "Verification Failed", "Incorrect master password. Access denied.")
                    return
            else:
                self.pwd_container.hide()

        # Check if username already exists in database (case-insensitive)
        try:
            embeddings = load_embeddings()
            existing_user_key = None
            for key in embeddings.keys():
                if key.lower() == username.lower():
                    existing_user_key = key
                    break

            if existing_user_key:
                if self.target_username:
                    # In explicit re-enrollment mode: allow proceeding for the target user
                    username = existing_user_key
                else:
                    # In 'Enroll New Face' mode: STRICTLY BLOCK duplicate username!
                    self.username_input.setStyleSheet("QLineEdit { border: 1.5px solid #ef4444; }")
                    self.username_input.setFocus()
                    QMessageBox.warning(
                        self, "User Already Enrolled",
                        f"User '{existing_user_key}' is already enrolled in the system vault.\n\n"
                        f"Duplicate usernames are not allowed. To update or re-enroll this user's facial profile, "
                        f"please click the 'Re-Enroll' button next to their profile in Settings."
                    )
                    return
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to check existing entries: {e}")
            return

        self.username = username
        self.start_capture_flow()

    # ------------------ Guided Capture Flow ------------------
    
    def start_capture_flow(self):
        self.stack.setCurrentIndex(1)
        self.intro_next_btn.setDefault(False)
        self.save_btn.setDefault(False)
        self.embeddings = []
        self.progress_bar.setValue(0)

        # Initialize detector asynchronously to prevent window freezing
        if not self.detector:
            self.instruction_lbl.setText("Initializing face recognition detector (may take a few seconds)...")
            from ui.auth_dialog import DetectorLoader
            self.loader = DetectorLoader(self)
            self.loader.loaded.connect(self.on_detector_loaded)
            self.loader.error.connect(self.on_detector_load_error)
            self.loader.start()
        else:
            self.start_camera_worker()

    def on_detector_loaded(self, detector):
        self.detector = detector
        self.start_camera_worker()

    def on_detector_load_error(self, err_msg):
        QMessageBox.critical(self, "Model Load Error", f"Failed to load detector models: {err_msg}")
        self.stack.setCurrentIndex(0)
        self.intro_next_btn.setDefault(True)
        self.save_btn.setDefault(False)
        self.username_input.setFocus()

    def start_camera_worker(self):
        self.instruction_lbl.setText("Initializing camera capture...")
        if hasattr(self, "detector") and self.detector:
            self.detector_worker = FaceDetectorWorker(self.detector)
            self.detector_worker.detected.connect(self.on_detection_result)
            self.detector_worker.start()

        self.camera_worker = CameraWorker()
        self.camera_worker.signals.frame_ready.connect(self.on_frame_received, Qt.ConnectionType.QueuedConnection)
        self.camera_worker.signals.error.connect(self.on_camera_error, Qt.ConnectionType.QueuedConnection)
        self.camera_worker.start()

    def cancel_capture_flow(self):
        self.cleanup_camera()
        self.stack.setCurrentIndex(0)
        self.intro_next_btn.setDefault(True)
        self.save_btn.setDefault(False)
        self.username_input.setFocus()

    @Slot(object)
    def on_frame_received(self, frame):
        # 1. Update live preview label on UI thread immediately (buttery smooth FPS)
        pixmap = convert_cv_to_pixmap(frame, 360, 270)
        self.camera_label.setPixmap(pixmap)

        # 2. Submit frame to background face detection thread
        if hasattr(self, "detector_worker") and self.detector_worker:
            self.detector_worker.submit_frame(frame)

    @Slot(list, object)
    def on_detection_result(self, faces, frame):
        if len(self.embeddings) >= self.required_frames:
            return

        # Update Guided instructions
        current_count = len(self.embeddings)
        if current_count < 5:
            self.instruction_lbl.setText("🟢 Look directly at the camera (straight ahead)")
        elif current_count < 10:
            self.instruction_lbl.setText("🟡 Turn your head slightly to the LEFT")
        elif current_count < 15:
            self.instruction_lbl.setText("🔵 Turn your head slightly to the RIGHT")

        # Check Blurriness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if is_blurry(gray):
            return

        if not faces:
            return
        if len(faces) > 1:
            self.instruction_lbl.setText("⚠️ Multiple faces detected! Make sure only one person is visible.")
            return

        emb = faces[0]['embedding']
        self.embeddings.append(emb)
        self.progress_bar.setValue(len(self.embeddings))

        # Check if capture finished
        if len(self.embeddings) >= self.required_frames:
            self.cleanup_camera()
            mean_emb = np.mean(self.embeddings, axis=0)
            norm = np.linalg.norm(mean_emb)
            self.avg_embedding = mean_emb / norm if norm > 0 else mean_emb

            # Check duplicate face vector against existing database entries
            self.duplicate_user = None
            self.duplicate_similarity = 0.0
            try:
                existing_embeddings = load_embeddings()
                from recognition.matcher import cosine_similarity
                from utils.config_loader import get_config
                thresh = float(get_config().get("recognition.similarity_threshold", 0.52))

                for uname, emb_vector in existing_embeddings.items():
                    if uname.lower() == self.username.lower():
                        continue
                    sim = cosine_similarity(self.avg_embedding, emb_vector)
                    if sim > self.duplicate_similarity:
                        self.duplicate_similarity = sim
                        if sim >= thresh:
                            self.duplicate_user = uname
            except Exception as e:
                logging.error(f"Error checking duplicate face embedding: {e}")

            self.show_success_page()

    @Slot(str)
    def on_camera_error(self, err_msg):
        self.cleanup_camera()
        QMessageBox.critical(self, "Camera Error", f"Camera capture failed: {err_msg}")
        self.stack.setCurrentIndex(0)
        self.intro_next_btn.setDefault(True)
        self.save_btn.setDefault(False)
        self.username_input.setFocus()

    def show_success_page(self):
        if getattr(self, "duplicate_user", None):
            self.success_msg_lbl.setText(
                f"⚠️ <b>Duplicate Face Profile Detected</b>\n\n"
                f"Successfully captured {self.required_frames} face frames for '{self.username}', but this face "
                f"matches an existing enrolled profile in the vault: <b>'{self.duplicate_user}'</b> "
                f"(Similarity Score: {self.duplicate_similarity * 100:.1f}%).\n\n"
                f"Enrolling identical faces under different usernames will cause authentication ambiguity conflicts.\n\n"
                f"Click 'Save Face Profile' below to proceed, or Cancel to update existing profile instead."
            )
        else:
            self.success_msg_lbl.setText(
                f"Guided capture succeeded!\n\n"
                f"Successfully captured {self.required_frames} face frames for user '{self.username}'. "
                f"The frames have been averaged to generate a high-quality facial template. "
                f"No raw images or frames have been saved to disk, keeping your biometric data private.\n\n"
                f"Click 'Save Face Profile' below to encrypt and save the profile."
            )
        self.stack.setCurrentIndex(2)
        self.save_btn.setDefault(True)
        self.save_btn.setFocus()

    def save_enrollment(self):
        if self.avg_embedding is None:
            QMessageBox.critical(self, "Save Error", "No embedding model is active.")
            self.reject()
            return

        try:
            save_embedding(self.username, self.avg_embedding)
            QMessageBox.information(self, "Success", f"Facial profile saved successfully for '{self.username}'.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Failed to write to database: {e}")
            self.reject()

    # ------------------ Cleanup ------------------

    def cleanup_camera(self):
        if hasattr(self, "detector_worker") and self.detector_worker:
            try:
                self.detector_worker.stop()
            except Exception:
                pass
            self.detector_worker = None

        if self.camera_worker:
            try:
                self.camera_worker.signals.frame_ready.disconnect(self.on_frame_received)
                self.camera_worker.signals.error.disconnect(self.on_camera_error)
            except Exception:
                pass
            try:
                self.camera_worker.stop()
            except Exception:
                pass
            self.camera_worker = None

        # Clear preview box
        self.camera_label.clear()

    def closeEvent(self, event):
        self.cleanup_camera()
        super().closeEvent(event)

    def reject(self):
        self.cleanup_camera()
        super().reject()

    def apply_theme_dynamically(self):
        from ui.theme import get_theme_qss, get_colors
        c = get_colors(self.theme_mode)
        self.setStyleSheet(get_theme_qss(self.theme_mode) + f"""
            QLabel#wizardHeader {{
                font-size: 20px;
                font-weight: bold;
                color: {c["TEXT_PRIMARY"]};
            }}
            QLabel#guidedHeader {{
                font-size: 18px;
                font-weight: bold;
                color: {c["TEXT_PRIMARY"]};
            }}
            QLabel#successHeader {{
                font-size: 20px;
                font-weight: bold;
                color: #10b981;
            }}
            QLabel#wizardDesc {{
                font-size: 13px;
                color: {c["TEXT_SECONDARY"]};
            }}
            QLabel#boldLabel {{
                font-weight: bold;
                font-size: 13px;
                color: {c["TEXT_PRIMARY"]};
            }}
            QLabel#warningLabel {{
                font-weight: bold;
                font-size: 13px;
                color: {c["WARNING_AMBER"]};
            }}
            QLabel#instructionLabel {{
                font-size: 14px;
                font-weight: bold;
                color: {c["WARNING_AMBER"]};
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
            self.camera_label.setStyleSheet(f"background-color: {c['CARD_NEUTRAL']}; border: 1px solid {c['BORDER_NEUTRAL']}; border-radius: 8px;")
        if hasattr(self, "title_bar") and self.title_bar:
            self.title_bar.apply_theme_dynamically()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idx = self.stack.currentIndex()
            if idx == 0:
                self.process_intro_next()
            elif idx == 2:
                self.save_enrollment()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
        else:
            super().keyPressEvent(event)
