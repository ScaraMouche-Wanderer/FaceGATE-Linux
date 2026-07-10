import os
import sys
import time
import logging
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QStackedWidget, QWidget, QMessageBox
)
from PySide6.QtCore import Qt, QSize, Slot, QTimer
from PySide6.QtGui import QIcon, QPixmap
from camera.camera_worker import CameraWorker
from recognition.detector import Detector
from recognition.blur_checker import is_blurry
from database.embedding_store import save_embedding, load_embeddings, get_cached_key
from security.credential_store import verify_password
from ui.auth_dialog import convert_cv_to_pixmap

class EnrollmentWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.detector = None
        self.camera_worker = None
        
        self.username = ""
        self.embeddings = []
        self.required_frames = 15
        self.processing_fps_limiter = 0.0 # Time threshold
        self.last_frame_processed_time = 0.0
        self.avg_embedding = None
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("FaceGate Enrollment Wizard")
        self.setFixedSize(500, 520)
        self.setModal(True)

        # Apply global theme stylesheet
        from ui.theme import get_theme_qss
        self.setStyleSheet(get_theme_qss())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # 1. Page 0: Intro & Username input & password validation if needed
        self.create_intro_page()
        
        # 2. Page 1: Capture with live camera and instructions
        self.create_capture_page()
        
        # 3. Page 2: Success review and confirm
        self.create_success_page()

        self.stack.setCurrentIndex(0)

    # ------------------ Page Creation ------------------
    
    def create_intro_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        from ui.theme import TEXT_PRIMARY, TEXT_SECONDARY
        header = QLabel("Enrolled User Setup")
        header.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(header)

        desc = QLabel("Welcome to the guided FaceGate user enrollment. Enter the username you want to associate with your facial profile.")
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; line-height: 1.4;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Username Input
        u_layout = QVBoxLayout()
        u_layout.setSpacing(6)
        u_lbl = QLabel("Enrolling Username:")
        u_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("e.g. voidnode")
        u_layout.addWidget(u_lbl)
        u_layout.addWidget(self.username_input)
        layout.addLayout(u_layout)

        # Password validation if key not cached
        self.pwd_container = QWidget()
        pwd_layout = QVBoxLayout(self.pwd_container)
        pwd_layout.setContentsMargins(0, 0, 0, 0)
        pwd_layout.setSpacing(6)
        
        from ui.theme import WARNING_AMBER
        pwd_lbl = QLabel("Enter Master Password to Unlock Database:")
        pwd_lbl.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {WARNING_AMBER};")
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
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

        from ui.theme import TEXT_PRIMARY, WARNING_AMBER
        self.guided_lbl = QLabel("Face Guided Capture")
        self.guided_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(self.guided_lbl)

        # Instructions
        self.instruction_lbl = QLabel("Starting camera...")
        self.instruction_lbl.setStyleSheet(f"color: {WARNING_AMBER}; font-size: 14px; font-weight: bold;")
        self.instruction_lbl.setWordWrap(True)
        self.instruction_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.instruction_lbl)

        # Video Frame box
        self.camera_label = QLabel()
        self.camera_label.setFixedSize(360, 270)
        self.camera_label.setStyleSheet("background-color: #1a1a1e; border: 1px solid #2d2d34; border-radius: 8px;")
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
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #10b981;")
        layout.addWidget(header)

        from ui.theme import TEXT_SECONDARY
        self.success_msg_lbl = QLabel()
        self.success_msg_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; line-height: 1.4;")
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

        # Handle password validation if key is not cached
        if get_cached_key() is None:
            password = self.pwd_input.text()
            if not password:
                QMessageBox.warning(self, "Password Required", "Master password is required to decrypt/update database.")
                return
            
            # Verify and cache key in memory
            if not verify_password(password):
                QMessageBox.critical(self, "Verification Failed", "Incorrect master password. Access denied.")
                return
            
            # Key successfully cached. Hide password input
            self.pwd_container.hide()

        # Check if username already exists in database
        try:
            embeddings = load_embeddings()
            if username in embeddings:
                res = QMessageBox.question(
                    self, "Overwrite User?", 
                    f"User '{username}' already exists in database.\n\n"
                    "Do you want to overwrite their facial profile with the new capture?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if res != QMessageBox.StandardButton.Yes:
                    return
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to check existing entries: {e}")
            return

        self.username = username
        self.start_capture_flow()

    # ------------------ Guided Capture Flow ------------------
    
    def start_capture_flow(self):
        self.stack.setCurrentIndex(1)
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

    def start_camera_worker(self):
        self.instruction_lbl.setText("Initializing camera capture...")
        self.camera_worker = CameraWorker()
        self.camera_worker.signals.frame_ready.connect(self.on_frame_received)
        self.camera_worker.signals.error.connect(self.on_camera_error)
        self.camera_worker.start()

    def cancel_capture_flow(self):
        self.cleanup_camera()
        self.stack.setCurrentIndex(0)

    @Slot(object)
    def on_frame_received(self, frame):
        # 1. Update live preview label
        pixmap = convert_cv_to_pixmap(frame, 360, 270)
        self.camera_label.setPixmap(pixmap)
        
        # 2. Limit extraction rate (e.g. process max 10 frames per second to avoid UI lag)
        current_time = time.time()
        if current_time - self.last_frame_processed_time < 0.1:
            return
        
        self.last_frame_processed_time = current_time

        # Update Guided instructions
        current_count = len(self.embeddings)
        if current_count < 5:
            self.instruction_lbl.setText("🟢 Look directly at the camera (straight ahead)")
        elif current_count < 10:
            self.instruction_lbl.setText("🟡 Turn your head slightly to the LEFT")
        elif current_count < 15:
            self.instruction_lbl.setText("🔵 Turn your head slightly to the RIGHT")
            
        # 3. Check Blurriness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if is_blurry(gray):
            # Do not display error to avoid distracting user, just skip frame
            return

        # 4. Detect face and extract embedding
        try:
            faces = self.detector.detect_faces(frame)
            # RAW FRAMES DISCARDED IMMEDIATELY AFTER extraction (no local writes)
            
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
                self.avg_embedding = np.mean(self.embeddings, axis=0)
                self.show_success_page()
                
        except Exception as e:
            logging.error(f"Error extracting face embedding: {e}")

    @Slot(str)
    def on_camera_error(self, err_msg):
        self.cleanup_camera()
        QMessageBox.critical(self, "Camera Error", f"Camera capture failed: {err_msg}")
        self.stack.setCurrentIndex(0)

    def show_success_page(self):
        self.success_msg_lbl.setText(
            f"Guided capture succeeded!\n\n"
            f"Successfully captured {self.required_frames} face frames for user '{self.username}'. "
            f"The frames have been averaged to generate a high-quality facial template. "
            f"No raw images or frames have been saved to disk, keeping your biometric data private.\n\n"
            f"Click 'Save Face Profile' below to encrypt and save the profile."
        )
        self.stack.setCurrentIndex(2)

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
        if self.camera_worker:
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
