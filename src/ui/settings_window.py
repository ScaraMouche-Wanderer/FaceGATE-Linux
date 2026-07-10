import os
import shutil
import subprocess
import logging
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QStackedWidget,
    QWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QSpinBox, QCheckBox, QMessageBox, QLineEdit, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
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
        self.resize(820, 540)
        self.setMinimumSize(750, 500)
        
        from ui.theme import get_theme_qss, ACCENT_CYAN, BORDER_NEUTRAL
        # Set base theme styling
        self.setStyleSheet(get_theme_qss() + f"""
            QListWidget#sidebar {{
                background-color: #0b0b0e;
                border: none;
                border-right: 1px solid {BORDER_NEUTRAL};
                padding-top: 10px;
                color: #94a3b8;
                font-size: 13px;
                font-weight: 500;
            }}
            QListWidget#sidebar::item {{
                padding: 10px 16px;
                border-radius: 6px;
                margin: 4px 8px;
            }}
            QListWidget#sidebar::item:hover {{
                background-color: #1a1a20;
                color: #ffffff;
            }}
            QListWidget#sidebar::item:selected {{
                background-color: {ACCENT_CYAN};
                color: #ffffff;
            }}
            QPushButton#removeBtn {{
                background-color: transparent;
                color: #ef4444;
                border: 1px solid #ef4444;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton#removeBtn:hover {{
                background-color: #ef4444;
                color: white;
            }}
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar Navigation
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(190)
        self.sidebar.setIconSize(QSize(18, 18))
        
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("system-lock-screen"), "Locked Apps"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("dialog-password"), "Authentication"))
        self.sidebar.addItem(QListWidgetItem(QIcon.fromTheme("preferences-system"), "Behavior"))
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
        self.create_logs_tab()
        self.create_about_tab()

        # Banner for daemon restart warning (initially hidden)
        from PySide6.QtWidgets import QFrame
        self.restart_banner = QFrame()
        self.restart_banner.setObjectName("restartBanner")
        self.restart_banner.setStyleSheet("""
            QFrame#restartBanner {
                background-color: #2d261e;
                border: 1px solid #d97706;
                border-radius: 6px;
            }
            QLabel {
                color: #fef3c7;
                font-size: 13px;
                border: none;
            }
            QPushButton {
                background-color: #d97706;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #b45309;
            }
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
        self.save_btn.clicked.connect(self.save_and_close)
        
        footer_layout.addWidget(self.cancel_btn)
        footer_layout.addWidget(self.save_btn)
        right_layout.addLayout(footer_layout)

        main_layout.addWidget(right_container)
        self.sidebar.setCurrentRow(0)

    def switch_tab(self, index):
        self.tab_stack.setCurrentIndex(index)
        if index == 3:
            self.populate_logs_table()

    def show_restart_banner(self):
        self.restart_banner.show()

    def restart_daemon(self):
        from utils.systemd_manager import restart
        if restart():
            QMessageBox.information(self, "Restart Successful", "FaceGate daemon has been restarted successfully.")
            self.restart_banner.hide()
        else:
            QMessageBox.critical(self, "Restart Failed", "Failed to restart FaceGate daemon via systemd user manager.")

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

        from ui.theme import get_card_qss, SUCCESS_GREEN
        # Master Password Config Card (Accent Border)
        card1 = QWidget()
        card1.setObjectName("card")
        card1.setStyleSheet(get_card_qss("accent"))
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
        
        self.enroll_btn = QPushButton("Enroll New Face (GUI)...")
        self.enroll_btn.setStyleSheet(f"background-color: {SUCCESS_GREEN};")
        self.enroll_btn.clicked.connect(self.open_enrollment_wizard)
        
        h_btn_layout = QHBoxLayout()
        h_btn_layout.addWidget(self.change_pwd_btn)
        h_btn_layout.addWidget(self.enroll_btn)
        h_btn_layout.addStretch()
        c1_layout.addLayout(h_btn_layout)
        
        layout.addWidget(card1)

        # Primitives Specs Card (Normal Border)
        card2 = QWidget()
        card2.setObjectName("card")
        card2.setStyleSheet(get_card_qss("normal"))
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

    def open_enrollment_wizard(self):
        from ui.enrollment_wizard import EnrollmentWizard
        dialog = EnrollmentWizard(self)
        dialog.exec()

    def create_behavior_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QLabel("Daemon Behavior & Protection")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        from ui.theme import get_card_qss, ACCENT_CYAN
        from PySide6.QtWidgets import QFormLayout

        # --- 1. Startup Group ---
        startup_card = QWidget()
        startup_card.setObjectName("card")
        startup_card.setStyleSheet(get_card_qss("normal"))
        startup_layout = QVBoxLayout(startup_card)
        startup_layout.setContentsMargins(16, 16, 16, 16)
        startup_layout.setSpacing(10)

        startup_lbl = QLabel("Startup Options")
        startup_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {ACCENT_CYAN};")
        startup_layout.addWidget(startup_lbl)

        self.autostart_check = QCheckBox("Launch FaceGate background daemon automatically at Login")
        startup_layout.addWidget(self.autostart_check)

        delay_layout = QHBoxLayout()
        delay_lbl = QLabel("Daemon startup delay (seconds):")
        delay_lbl.setStyleSheet("font-size: 13px; color: #cbd5e0;")
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 60)
        delay_layout.addWidget(delay_lbl)
        delay_layout.addWidget(self.delay_spin)
        delay_layout.addStretch()
        startup_layout.addLayout(delay_layout)

        layout.addWidget(startup_card)

        # --- 2. Locking Policy Group ---
        policy_card = QWidget()
        policy_card.setObjectName("card")
        policy_card.setStyleSheet(get_card_qss("normal"))
        policy_layout = QVBoxLayout(policy_card)
        policy_layout.setContentsMargins(16, 16, 16, 16)
        policy_layout.setSpacing(10)

        policy_lbl = QLabel("Locking & Timeout Policies")
        policy_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {ACCENT_CYAN};")
        policy_layout.addWidget(policy_lbl)

        policy_form = QFormLayout()
        policy_form.setSpacing(10)
        policy_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.policy_combo = QComboBox()
        self.policy_combo.addItem("Kill Process (SIGKILL)", "kill")
        self.policy_combo.addItem("Keep Process Stopped (SIGSTOP)", "keep_stopped")
        policy_form.addRow("On Auth Failure Policy:", self.policy_combo)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSingleStep(5)
        policy_form.addRow("GUI Timeout (seconds):", self.timeout_spin)

        policy_layout.addLayout(policy_form)
        layout.addWidget(policy_card)

        # --- 3. Protection Group (Danger Red Highlight) ---
        prot_card = QWidget()
        prot_card.setObjectName("card")
        prot_card.setStyleSheet(get_card_qss("danger"))
        prot_layout = QVBoxLayout(prot_card)
        prot_layout.setContentsMargins(16, 16, 16, 16)
        prot_layout.setSpacing(10)

        prot_lbl = QLabel("System Protection & Emergency Settings")
        prot_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #ef4444;")
        prot_layout.addWidget(prot_lbl)

        self.protection_check = QCheckBox("App Deletion Protection (highly recommended)")
        self.protection_check.clicked.connect(self.handle_protection_clicked)
        prot_layout.addWidget(self.protection_check)

        hk_layout = QHBoxLayout()
        hk_lbl = QLabel("Emergency Kill Shortcut:")
        hk_lbl.setStyleSheet("font-size: 13px; color: #cbd5e0;")
        self.hotkey_input = QLineEdit()
        self.hotkey_input.setPlaceholderText("<Control><Alt>k")
        hk_layout.addWidget(hk_lbl)
        hk_layout.addWidget(self.hotkey_input)
        hk_layout.addStretch()
        prot_layout.addLayout(hk_layout)

        hk_desc = QLabel("GNOME format: e.g. <Control><Alt>k or <Shift><Control><Alt>e")
        hk_desc.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        prot_layout.addWidget(hk_desc)

        layout.addWidget(prot_card)

        # --- 4. Notifications & Idle Group ---
        notif_card = QWidget()
        notif_card.setObjectName("card")
        notif_card.setStyleSheet(get_card_qss("normal"))
        notif_layout = QVBoxLayout(notif_card)
        notif_layout.setContentsMargins(16, 16, 16, 16)
        notif_layout.setSpacing(10)

        notif_lbl = QLabel("Notifications & Idle Locks")
        notif_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {ACCENT_CYAN};")
        notif_layout.addWidget(notif_lbl)

        self.notify_check = QCheckBox("Show desktop notifications on application unlock/relock")
        notif_layout.addWidget(self.notify_check)

        self.idle_check = QCheckBox("Auto re-lock protected applications on system idle (GNOME Stub)")
        notif_layout.addWidget(self.idle_check)

        idle_time_layout = QHBoxLayout()
        idle_time_lbl = QLabel("Idle timeout (minutes):")
        idle_time_lbl.setStyleSheet("font-size: 13px; color: #cbd5e0;")
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(1, 60)
        self.idle_spin.setEnabled(False)
        self.idle_check.stateChanged.connect(lambda state: self.idle_spin.setEnabled(state == Qt.CheckState.Checked.value))
        idle_time_layout.addWidget(idle_time_lbl)
        idle_time_layout.addWidget(self.idle_spin)
        idle_time_layout.addStretch()
        notif_layout.addLayout(idle_time_layout)

        layout.addWidget(notif_card)
        layout.addStretch()

        self.tab_stack.addWidget(page)

    def create_logs_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Security Audit Logs")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        desc = QLabel("View recent application authorization attempts and outcomes.")
        desc.setStyleSheet("color: #a0aec0; font-size: 13px;")
        layout.addWidget(desc)

        # Filter Chips/Dropdown Layout
        filter_layout = QHBoxLayout()
        filter_lbl = QLabel("Filter status:")
        filter_lbl.setStyleSheet("color: #94a3b8; font-size: 13px; font-weight: 500;")
        
        self.log_filter_combo = QComboBox()
        self.log_filter_combo.addItems(["All Attempts", "Success", "Failed", "Timeout", "Bypass"])
        self.log_filter_combo.currentIndexChanged.connect(self.populate_logs_table)
        
        filter_layout.addWidget(filter_lbl)
        filter_layout.addWidget(self.log_filter_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Tree Widget for logs
        self.logs_tree = QTreeWidget()
        self.logs_tree.setColumnCount(5)
        self.logs_tree.setHeaderLabels(["Time", "Application", "Method", "Result", "Confidence"])
        self.logs_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.logs_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.logs_tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        layout.addWidget(self.logs_tree)

        # Empty state label
        self.logs_empty_label = QLabel("No authentication activity yet")
        self.logs_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logs_empty_label.setStyleSheet("color: #94a3b8; font-size: 14px; font-style: italic; padding: 40px;")
        layout.addWidget(self.logs_empty_label)
        self.logs_empty_label.hide()

        self.tab_stack.addWidget(page)

    def create_about_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QLabel("About FaceGate-Linux")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        from ui.theme import get_card_qss
        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet(get_card_qss("normal"))
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        logo = QLabel("🔒 FaceGate-Linux")
        logo.setStyleSheet("font-size: 24px; font-weight: bold; color: #0ea5e9; border: none;")
        card_layout.addWidget(logo)

        version = QLabel("Version: 0.1.0 (Phase 8 Build)")
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
        
        # 3. Autostart & Protection
        self.autostart_check.setChecked(is_enabled())
        self.protection_check.setChecked(self.config.get("behavior.uninstall_protection", True))
        
        # 4. Emergency Kill Hotkey
        hotkey = self.config.get("behavior.emergency_key", "<Control><Alt>k")
        self.hotkey_input.setText(hotkey)

        # 5. New behavior settings
        self.notify_check.setChecked(self.config.get("behavior.notify_on_auth", True))
        self.idle_check.setChecked(self.config.get("behavior.autolock_on_idle", False))
        self.idle_spin.setValue(self.config.get("behavior.autolock_on_idle_minutes", 10))
        self.idle_spin.setEnabled(self.idle_check.isChecked())
        self.delay_spin.setValue(self.config.get("behavior.startup_delay_seconds", 0))

        # 6. Populate Logs Table
        self.populate_logs_table()

        # Connect signals for restart indicator after initial populate
        self.policy_combo.currentIndexChanged.connect(self.show_restart_banner)
        self.timeout_spin.valueChanged.connect(self.show_restart_banner)
        self.protection_check.stateChanged.connect(self.show_restart_banner)
        self.hotkey_input.textChanged.connect(self.show_restart_banner)
        self.notify_check.stateChanged.connect(self.show_restart_banner)
        self.idle_check.stateChanged.connect(self.show_restart_banner)
        self.idle_spin.valueChanged.connect(self.show_restart_banner)
        self.delay_spin.valueChanged.connect(self.show_restart_banner)

    def populate_apps_table(self):
        self.apps_table.setRowCount(len(self.current_apps))
        for row, app in enumerate(self.current_apps):
            # Resolve QIcon using shared utility
            from ui.theme import resolve_app_icon
            icon = resolve_app_icon(app.get("icon", ""))
            
            icon_item = QTableWidgetItem(app.get("name", ""))
            icon_item.setIcon(icon)
            
            id_item = QTableWidgetItem(app.get("id", ""))
            
            # Action Remove Button
            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("removeBtn")
            remove_btn.clicked.connect(self.make_remove_callback(row))
            
            self.apps_table.setItem(row, 0, icon_item)
            self.apps_table.setItem(row, 1, id_item)
            self.apps_table.setCellWidget(row, 2, remove_btn)

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
            
            from PySide6.QtGui import QFont
            font = header_item.font(0)
            font.setBold(True)
            header_item.setFont(0, font)
            self.logs_tree.addTopLevelItem(header_item)

            for time_part, log in items:
                app_identifier = log["app_identifier"]
                method = log["method"].upper()
                res = log["result"].upper()
                score_str = f"{log['confidence_score']:.4f}" if log["confidence_score"] is not None else "N/A"

                child_item = QTreeWidgetItem([
                    time_part,
                    app_identifier,
                    method,
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
                child_item.setIcon(3, create_status_icon(icon_color))

                header_item.addChild(child_item)

        self.logs_tree.expandAll()

    def make_remove_callback(self, index):
        return lambda: self.remove_app_at(index)

    # ------------------ Actions ------------------
    
    def remove_app_at(self, index):
        if 0 <= index < len(self.current_apps):
            app = self.current_apps[index]
            self.current_apps.pop(index)
            self.populate_apps_table()
            self.show_restart_banner()
            logging.info(f"Staged app removal: '{app.get('id')}'")

    def open_app_picker(self):
        dialog = AppPickerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_app:
            app_data = dialog.selected_app
            
            new_app = {
                "id": app_data["executable"],
                "name": app_data["name"],
                "executable": app_data["executable"],
                "desktop_name": app_data["desktop_name"]
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

    def handle_protection_clicked(self, checked):
        # Disabling protection requires master password auth
        if not checked:
            logging.info("Request to disable App Deletion Protection. Requiring master password.")
            from ui.auth_dialog import AuthDialog
            dialog = AuthDialog("Disable Deletion Protection", mode="password", parent=self)
            res = dialog.exec()
            if res != QDialog.DialogCode.Accepted:
                self.protection_check.setChecked(True)
                QMessageBox.warning(self, "Verification Failed", "Incorrect password. App Deletion Protection remains active.")
            else:
                logging.info("App Deletion Protection successfully disabled.")

    def trigger_password_change(self):
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

        from locking.launcher_sub import get_facegate_executable
        facegate_exe = get_facegate_executable()
        
        try:
            if term_bin in ("gnome-terminal", "konsole", "xfce4-terminal"):
                subprocess.Popen([term_bin, "--", facegate_exe, "--set-master-password"])
            elif term_bin == "kitty":
                subprocess.Popen([term_bin, facegate_exe, "--set-master-password"])
            else:
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
        self.config.set("behavior.uninstall_protection", self.protection_check.isChecked())
        self.config.set("app_monitor.on_auth_failure", self.policy_combo.itemData(self.policy_combo.currentIndex()))
        self.config.set("app_monitor.auth_timeout_seconds", self.timeout_spin.value())
        self.config.set("behavior.notify_on_auth", self.notify_check.isChecked())
        self.config.set("behavior.autolock_on_idle", self.idle_check.isChecked())
        self.config.set("behavior.autolock_on_idle_minutes", self.idle_spin.value())
        self.config.set("behavior.startup_delay_seconds", self.delay_spin.value())
        
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
