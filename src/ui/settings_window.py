import os
import sys
import shutil
import subprocess
import logging
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QStackedWidget,
    QWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QSpinBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QFont
from utils.config_loader import get_config
from utils.systemd_manager import is_enabled, enable, disable
from ui.app_picker_dialog import AppPickerDialog
from locking.launcher_sub import apply_substitution, restore_substitution

class SettingsWindow(QDialog):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config if config else get_config()
        
        # Keep track of initial apps list to perform delta substitutions on Save
        self.initial_apps = list(self.config.get("protected_apps", []))
        self.current_apps = list(self.initial_apps)
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle("FaceGate Settings")
        self.resize(780, 520)
        self.setMinimumSize(700, 480)
        
        # Modern Premium QSS Style
        self.setStyleSheet("""
            QDialog {
                background-color: #121214;
                color: #e2e8f0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #e2e8f0;
            }
            QListWidget#sidebar {
                background-color: #1a1a1e;
                border: none;
                border-right: 1px solid #2d2d34;
                padding-top: 10px;
                color: #a0aec0;
                font-size: 14px;
                font-weight: 500;
            }
            QListWidget#sidebar::item {
                padding: 12px 20px;
                border-radius: 6px;
                margin: 4px 8px;
            }
            QListWidget#sidebar::item:hover {
                background-color: #2d2d34;
                color: #ffffff;
            }
            QListWidget#sidebar::item:selected {
                background-color: #4f46e5;
                color: #ffffff;
            }
            QTableWidget {
                background-color: #1a1a1e;
                border: 1px solid #2d2d34;
                gridline-color: #2d2d34;
                color: #e2e8f0;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QHeaderView::section {
                background-color: #2d2d34;
                color: #cbd5e0;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QComboBox, QSpinBox {
                background-color: #1a1a1e;
                border: 1px solid #3a3a44;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 13px;
            }
            QComboBox:focus, QSpinBox:focus {
                border: 1px solid #6366f1;
            }
            QCheckBox {
                spacing: 8px;
                color: #e2e8f0;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #3a3a44;
                background-color: #1a1a1e;
            }
            QCheckBox::indicator:checked {
                background-color: #4f46e5;
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
            }
            QPushButton:hover {
                background-color: #4338ca;
            }
            QPushButton:pressed {
                background-color: #3730a3;
            }
            QPushButton#cancelBtn {
                background-color: #2d2d34;
                color: #cbd5e0;
            }
            QPushButton#cancelBtn:hover {
                background-color: #3a3a44;
            }
            QPushButton#removeBtn {
                background-color: transparent;
                color: #ef4444;
                border: 1px solid #ef4444;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#removeBtn:hover {
                background-color: #ef4444;
                color: white;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar Navigation
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(190)
        self.sidebar.setIconSize(QSize(18, 18))
        
        # Load sidebar icons (using system themes where appropriate)
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("system-lock-screen"), "Locked Apps"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("dialog-password"), "Authentication"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("preferences-system"), "Behavior"))
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
        self.create_about_tab()

        right_layout.addWidget(self.tab_stack)

        # Footer Actions (Save / Cancel / Warning)
        footer_layout = QHBoxLayout()
        
        self.warn_label = QLabel("⚠️ Restart FaceGate for changes to take effect")
        self.warn_label.setStyleSheet("color: #fbbf24; font-weight: 500; font-size: 12px;")
        footer_layout.addWidget(self.warn_label)
        footer_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self.save_and_close)
        
        footer_layout.addWidget(self.cancel_btn)
        footer_layout.addWidget(self.save_btn)
        right_layout.addLayout(footer_layout)

        main_layout.addWidget(right_container)
        self.sidebar.setCurrentRow(0)

    def switch_tab(self, index):
        self.tab_stack.setCurrentIndex(index)

    # ------------------ Tab Creation Methods ------------------
    
    def create_locked_apps_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Locked Applications")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        desc = QLabel("Manage applications that trigger face recognition authentication on launch.")
        desc.setStyleSheet("color: #a0aec0; font-size: 13px;")
        layout.addWidget(desc)

        # Table
        self.apps_table = QTableWidget()
        self.apps_table.setColumnCount(3)
        self.apps_table.setHorizontalHeaderLabels(["Application", "Identifier", "Action"])
        self.apps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.apps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.apps_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.apps_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.apps_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        layout.addWidget(self.apps_table)

        # Add Button
        self.add_app_btn = QPushButton("+ Add Application...")
        self.add_app_btn.clicked.connect(self.open_app_picker)
        layout.addWidget(self.add_app_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.tab_stack.addWidget(page)

    def create_authentication_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        header = QLabel("Authentication & Primitives")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        # Master Password Config Card
        card1 = QWidget()
        card1.setStyleSheet("background-color: #1a1a1e; border: 1px solid #2d2d34; border-radius: 8px;")
        c1_layout = QVBoxLayout(card1)
        c1_layout.setContentsMargins(16, 16, 16, 16)
        c1_layout.setSpacing(10)

        lbl1 = QLabel("Master Password")
        lbl1.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff; border: none;")
        c1_layout.addWidget(lbl1)

        lbl2 = QLabel("Configures the local master password that secures your face database envelope. "
                      "Updating the password will re-encrypt all credentials at rest under a new random KDF salt.")
        lbl2.setStyleSheet("color: #a0aec0; font-size: 13px; border: none;")
        lbl2.setWordWrap(True)
        c1_layout.addWidget(lbl2)

        self.change_pwd_btn = QPushButton("Change Master Password...")
        self.change_pwd_btn.clicked.connect(self.trigger_password_change)
        c1_layout.addWidget(self.change_pwd_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card1)

        # Primitives Specs Card
        card2 = QWidget()
        card2.setStyleSheet("background-color: #1a1a1e; border: 1px solid #2d2d34; border-radius: 8px;")
        c2_layout = QVBoxLayout(card2)
        c2_layout.setContentsMargins(16, 16, 16, 16)
        c2_layout.setSpacing(12)

        lbl3 = QLabel("Active Security Profiles")
        lbl3.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff; border: none;")
        c2_layout.addWidget(lbl3)

        # Read-only attributes layout
        self.kdf_label = QLabel("KDF: PBKDF2-HMAC-SHA256 (600,000 iterations)")
        self.kdf_label.setStyleSheet("color: #cbd5e0; font-size: 13px; border: none;")
        c2_layout.addWidget(self.kdf_label)

        self.cipher_label = QLabel("Cipher: AES-256-GCM (Authenticated Encrypt-then-MAC)")
        self.cipher_label.setStyleSheet("color: #cbd5e0; font-size: 13px; border: none;")
        c2_layout.addWidget(self.cipher_label)

        # Load values dynamically from config
        thresh = self.config.get("recognition.similarity_threshold", "0.65")
        margin = self.config.get("recognition.ambiguity_margin", "0.03")

        self.thresh_label = QLabel(f"Similarity Threshold: {thresh} (Required matching score)")
        self.thresh_label.setStyleSheet("color: #cbd5e0; font-size: 13px; border: none;")
        c2_layout.addWidget(self.thresh_label)

        self.margin_label = QLabel(f"Ambiguity Margin: {margin} (Required margin between top candidates)")
        self.margin_label.setStyleSheet("color: #cbd5e0; font-size: 13px; border: none;")
        c2_layout.addWidget(self.margin_label)

        layout.addWidget(card2)
        layout.addStretch()

        self.tab_stack.addWidget(page)

    def create_behavior_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QLabel("Daemon Behavior")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        # Form layout
        form = QWidget()
        form.setStyleSheet("background-color: #1a1a1e; border: 1px solid #2d2d34; border-radius: 8px;")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(16)

        # 1. Auth failure action policy
        h_layout1 = QHBoxLayout()
        lbl1 = QLabel("On Auth Failure Policy:")
        lbl1.setStyleSheet("font-size: 13px; color: #cbd5e0; border: none;")
        self.policy_combo = QComboBox()
        self.policy_combo.addItem("Kill Process (SIGKILL)", "kill")
        self.policy_combo.addItem("Keep Process Stopped (SIGSTOP)", "keep_stopped")
        h_layout1.addWidget(lbl1)
        h_layout1.addWidget(self.policy_combo)
        form_layout.addLayout(h_layout1)

        # 2. Recognition Dialog Timeout
        h_layout2 = QHBoxLayout()
        lbl2 = QLabel("GUI Timeout (seconds):")
        lbl2.setStyleSheet("font-size: 13px; color: #cbd5e0; border: none;")
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSingleStep(5)
        h_layout2.addWidget(lbl2)
        h_layout2.addWidget(self.timeout_spin)
        form_layout.addLayout(h_layout2)

        # 3. Systemd Auto-launch Checkbox
        h_layout3 = QHBoxLayout()
        self.autostart_check = QCheckBox("Launch FaceGate background daemon automatically at Login")
        self.autostart_check.setStyleSheet("border: none;")
        h_layout3.addWidget(self.autostart_check)
        form_layout.addLayout(h_layout3)

        layout.addWidget(form)
        layout.addStretch()

        self.tab_stack.addWidget(page)

    def create_about_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QLabel("About FaceGate-Linux")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        card = QWidget()
        card.setStyleSheet("background-color: #1a1a1e; border: 1px solid #2d2d34; border-radius: 8px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        logo = QLabel("🔒 FaceGate-Linux")
        logo.setStyleSheet("font-size: 24px; font-weight: bold; color: #6366f1; border: none;")
        card_layout.addWidget(logo)

        version = QLabel("Version: 0.1.0 (Phase 4 Build)")
        version.setStyleSheet("color: #cbd5e0; font-size: 13px; border: none; font-weight: bold;")
        card_layout.addWidget(version)

        desc = QLabel("FaceGate-Linux is a lightweight security wrapper daemon that locks system application launches "
                      "using face recognition. It combines process scanning, SIGSTOP interception, D-Bus session controls, "
                      "and authenticated AES-256-GCM data storage.")
        desc.setStyleSheet("color: #a0aec0; font-size: 13px; border: none; line-height: 1.4;")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        card_layout.addSpacing(10)
        
        info = QLabel("Written by Senior Linux Desktop Engineer.")
        info.setStyleSheet("color: #cbd5e0; font-size: 12px; border: none; font-style: italic;")
        card_layout.addWidget(info)

        layout.addWidget(card)
        layout.addStretch()

        self.tab_stack.addWidget(page)

    # ------------------ Loading Settings ------------------
    
    def load_settings(self):
        # 1. Apps Table
        self.populate_apps_table()
        
        # 2. Behavior
        policy = self.config.get("app_monitor.on_auth_failure", "kill")
        idx = self.policy_combo.findData(policy)
        if idx >= 0:
            self.policy_combo.setCurrentIndex(idx)
            
        timeout = self.config.get("app_monitor.auth_timeout_seconds", 60)
        self.timeout_spin.setValue(timeout)
        
        # 3. Systemd Login check
        self.autostart_check.setChecked(is_enabled())

    def populate_apps_table(self):
        self.apps_table.setRowCount(len(self.current_apps))
        for row, app in enumerate(self.current_apps):
            # Resolve Icon
            icon_item = QTableWidgetItem(app.get("name", ""))
            icon_source = app.get("icon", "")
            icon = None
            if icon_source:
                if os.path.isabs(icon_source) and os.path.exists(icon_source):
                    icon = QIcon(icon_source)
                else:
                    icon = QIcon.fromTheme(icon_source)
            if not icon or icon.isNull():
                icon = QIcon.fromTheme("application-x-executable")
                
            icon_item.setIcon(icon)
            
            id_item = QTableWidgetItem(app.get("id", ""))
            
            # Action Remove Button
            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("removeBtn")
            # Connect using closure to capture row index correctly
            remove_btn.clicked.connect(self.make_remove_callback(row))
            
            self.apps_table.setItem(row, 0, icon_item)
            self.apps_table.setItem(row, 1, id_item)
            self.apps_table.setCellWidget(row, 2, remove_btn)

    def make_remove_callback(self, index):
        return lambda: self.remove_app_at(index)

    # ------------------ Actions ------------------
    
    def remove_app_at(self, index):
        if 0 <= index < len(self.current_apps):
            app = self.current_apps[index]
            self.current_apps.pop(index)
            self.populate_apps_table()
            logging.info(f"Staged app removal: '{app.get('id')}'")

    def open_app_picker(self):
        dialog = AppPickerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_app:
            app_data = dialog.selected_app
            
            # Form the structure default.yaml expects
            new_app = {
                "id": app_data["executable"],
                "name": app_data["name"],
                "executable": app_data["executable"],
                "desktop_name": app_data["desktop_name"]
            }
            
            # Keep the icon path/name if present, so we can display it next time
            if app_data.get("icon"):
                new_app["icon"] = app_data["icon"]
                
            # Avoid duplicate registrations
            if any(a["id"] == new_app["id"] for a in self.current_apps):
                QMessageBox.warning(self, "Duplicate Application", 
                                    f"The application '{new_app['name']}' is already protected.")
                return
                
            self.current_apps.append(new_app)
            self.populate_apps_table()
            logging.info(f"Staged app protection addition: '{new_app['id']}'")

    def trigger_password_change(self):
        # Spawns credential_store CLI wrapper in terminal
        # Find terminal emulator
        terminals = ["kitty", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"]
        term_bin = None
        for term in terminals:
            if shutil.which(term):
                term_bin = term
                break
                
        if not term_bin:
            QMessageBox.critical(self, "No Terminal Found", 
                                 "Could not find a terminal emulator (kitty, gnome-terminal, xterm, etc.) to run the password setup CLI.")
            return

        # Resolve facegate path dynamically
        from locking.launcher_sub import get_facegate_executable
        facegate_exe = get_facegate_executable()
        
        # Build command depending on terminal emulator parameters
        try:
            if term_bin in ("gnome-terminal", "konsole", "xfce4-terminal"):
                subprocess.Popen([term_bin, "--", facegate_exe, "--set-master-password"])
            elif term_bin == "kitty":
                subprocess.Popen([term_bin, facegate_exe, "--set-master-password"])
            else: # xterm fallback
                subprocess.Popen([term_bin, "-e", f"{facegate_exe} --set-master-password"])
                
            logging.info(f"Spawned password setup in terminal: {term_bin}")
        except Exception as e:
            QMessageBox.critical(self, "Terminal Launch Failed", f"Failed to open terminal setup: {e}")

    # ------------------ Save Settings ------------------
    
    def save_and_close(self):
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
                # Call restore substitution for single app only
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

        # 3. Save behavior options to config default.yaml
        self.config.set("behavior.launch_at_login", should_autostart)
        self.config.set("app_monitor.on_auth_failure", self.policy_combo.itemData(self.policy_combo.currentIndex()))
        self.config.set("app_monitor.auth_timeout_seconds", self.timeout_spin.value())
        
        # Save updated protected apps
        self.config.set("protected_apps", self.current_apps)
        
        # Write config back to file
        if self.config.save():
            QMessageBox.information(self, "Settings Saved", 
                                    "Settings have been saved successfully.\n\n"
                                    "Please restart the FaceGate daemon to apply changes.")
            self.accept()
        else:
            QMessageBox.critical(self, "Save Failed", "Failed to save configuration parameters.")
