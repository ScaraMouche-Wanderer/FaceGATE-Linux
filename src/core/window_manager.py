"""
WindowManager for FaceGATE-Linux.

Manages instantiation, activation, and cleanup of the Settings and
Guided Enrollment GUI windows.
"""

import logging
from PySide6.QtCore import QObject, Slot, Qt

class WindowManager(QObject):
    def __init__(self, config, auth_coordinator, parent=None):
        super().__init__(parent)
        self.config = config
        self.auth_coordinator = auth_coordinator
        self._settings_window = None
        self._enrollment_wizard = None

    @Slot()
    def open_settings(self):
        if not self.auth_coordinator.verify_admin_face("Settings Access"):
            logging.warning("Settings Access: Verification failed.")
            return
            
        from ui.settings_window import SettingsWindow
        if self._settings_window is None:
            self._settings_window = SettingsWindow(self.config, parent=None)
            self._settings_window.finished.connect(self.cleanup_settings_window)
        self._settings_window.setWindowState(Qt.WindowState.WindowActive)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def cleanup_settings_window(self, result):
        self._settings_window = None

    @Slot()
    def open_enrollment(self):
        if not self.auth_coordinator.verify_admin_face("Enrollment Access"):
            logging.warning("Enrollment Access: Verification failed.")
            return

        from ui.enrollment_wizard import EnrollmentWizard
        if self._enrollment_wizard is None:
            self._enrollment_wizard = EnrollmentWizard(parent=None)
            self._enrollment_wizard.finished.connect(self.cleanup_enrollment_wizard)
        self._enrollment_wizard.setWindowState(Qt.WindowState.WindowActive)
        self._enrollment_wizard.show()
        self._enrollment_wizard.raise_()
        self._enrollment_wizard.activateWindow()

    def cleanup_enrollment_wizard(self, result):
        self._enrollment_wizard = None
