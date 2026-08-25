"""
Unit tests for the Modern Quick Settings Tray Popup and System Tray Integration.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QRect, QPoint, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent

from ui.tray_popup import (
    ModernToggleSwitch, ModernStepperControl, SegmentedChipGroup,
    AppRowWidget, ActionNavRow, FaceGateTrayPopup
)
from ui.tray import FaceGateTray, launch_app_command

# Ensure single QApplication instance in offscreen test environment
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


class TestModernToggleSwitch(unittest.TestCase):
    def setUp(self):
        self.switch = ModernToggleSwitch(checked=False)

    def test_initial_state(self):
        self.assertFalse(self.switch.isChecked())
        self.assertEqual(self.switch.knob_position, 0.0)

    def test_set_checked(self):
        self.switch.setChecked(True, animate=False)
        self.assertTrue(self.switch.isChecked())
        self.assertEqual(self.switch.knob_position, 1.0)

        self.switch.setChecked(False, animate=False)
        self.assertFalse(self.switch.isChecked())
        self.assertEqual(self.switch.knob_position, 0.0)

    def test_toggle_signal(self):
        received = []
        self.switch.toggled.connect(lambda val: received.append(val))

        self.switch.toggle()
        self.assertTrue(self.switch.isChecked())
        self.assertEqual(received, [True])

        self.switch.toggle()
        self.assertFalse(self.switch.isChecked())
        self.assertEqual(received, [True, False])

    def test_keyboard_toggle(self):
        received = []
        self.switch.toggled.connect(lambda val: received.append(val))

        # Test Space key
        space_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        self.switch.keyPressEvent(space_event)
        self.assertTrue(self.switch.isChecked())
        self.assertEqual(received, [True])

        # Test Enter key
        enter_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        self.switch.keyPressEvent(enter_event)
        self.assertFalse(self.switch.isChecked())
        self.assertEqual(received, [True, False])


class TestModernStepperControl(unittest.TestCase):
    def setUp(self):
        self.stepper = ModernStepperControl(value=15, min_val=5, max_val=60, step=5, suffix="m")

    def test_initial_value(self):
        self.assertEqual(self.stepper.value(), 15)
        self.assertEqual(self.stepper.lbl_value.text(), "15m")

    def test_increment_and_decrement(self):
        received = []
        self.stepper.valueChanged.connect(lambda val: received.append(val))

        self.stepper._increment()
        self.assertEqual(self.stepper.value(), 20)
        self.assertEqual(self.stepper.lbl_value.text(), "20m")

        self.stepper._decrement()
        self.assertEqual(self.stepper.value(), 15)
        self.assertEqual(self.stepper.lbl_value.text(), "15m")

    def test_clamping(self):
        self.stepper.setValue(100)
        self.assertEqual(self.stepper.value(), 60)

        self.stepper.setValue(1)
        self.assertEqual(self.stepper.value(), 5)

    def test_reset(self):
        self.stepper.setValue(45)
        self.assertEqual(self.stepper.value(), 45)
        self.stepper._reset()
        self.assertEqual(self.stepper.value(), 15)


class TestSegmentedChipGroup(unittest.TestCase):
    def setUp(self):
        self.chips = SegmentedChipGroup(presets=[("5m", 5), ("15m", 15), ("30m", 30)])

    def test_chip_selection(self):
        received = []
        self.chips.chipSelected.connect(lambda val: received.append(val))

        self.chips._on_chip_clicked(15, 1)
        self.assertEqual(received, [15])
        self.assertTrue(self.chips._buttons[1].isChecked())
        self.assertFalse(self.chips._buttons[0].isChecked())

        self.chips.clearSelection()
        self.assertFalse(any(b.isChecked() for b in self.chips._buttons))


class TestAppRowWidget(unittest.TestCase):
    def test_locked_app_row(self):
        app_data = {"id": "test_app", "name": "Test App", "desktop_name": "test.desktop", "icon": ""}
        row = AppRowWidget(app_data, is_authed=False)

        self.assertIn("Test App", row.name_lbl.text())
        self.assertIn("Locked", row.status_lbl.text())
        self.assertIn("Unlock", row.action_btn.text())

        received_auth = []
        row.authRequested.connect(lambda name: received_auth.append(name))
        row.action_btn.click()
        self.assertEqual(received_auth, ["test.desktop"])

    def test_unlocked_app_row(self):
        app_data = {"id": "test_app", "name": "Test App", "desktop_name": "test.desktop", "icon": ""}
        row = AppRowWidget(app_data, is_authed=True)

        self.assertIn("Unlocked", row.status_lbl.text())
        self.assertIn("Relock", row.action_btn.text())

        received_relock = []
        row.relockRequested.connect(lambda app_id: received_relock.append(app_id))
        row.action_btn.click()
        self.assertEqual(received_relock, ["test_app"])


class TestActionNavRow(unittest.TestCase):
    def test_action_nav_row_click(self):
        row = ActionNavRow("gear", "Settings", "Configure options")
        received = []
        row.clicked.connect(lambda: received.append(True))

        click_event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(5.0, 5.0), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        row.mousePressEvent(click_event)
        self.assertEqual(received, [True])

        enter_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        row.keyPressEvent(enter_event)
        self.assertEqual(received, [True, True])


class TestFaceGateTrayPopup(unittest.TestCase):
    def setUp(self):
        self.mock_main_app = MagicMock()
        self.mock_main_app.is_active.return_value = True
        self.mock_main_app.disabled_until = None
        self.mock_main_app.get_remaining_disabled_seconds.return_value = 0.0
        self.mock_main_app.get_protected_apps.return_value = [
            {"id": "chrome", "name": "Google Chrome", "desktop_name": "google-chrome.desktop", "show_in_tray": True},
            {"id": "terminal", "name": "Terminal", "desktop_name": "org.gnome.Terminal.desktop", "show_in_tray": True}
        ]
        self.mock_main_app.is_app_authorized.side_effect = lambda app_id: app_id == "terminal"

        self.popup = FaceGateTrayPopup(self.mock_main_app)

    def test_build_and_refresh_state_active(self):
        self.popup.refresh_state()
        self.assertTrue(self.popup.master_switch.isChecked())
        self.assertIn("Active", self.popup.lbl_subtitle.text())
        self.assertTrue(self.popup.btn_relock_all.isEnabled())  # terminal is authed
        self.assertEqual(self.popup.apps_container.count(), 2)

    def test_refresh_state_paused(self):
        self.mock_main_app.is_active.return_value = False
        self.mock_main_app.disabled_until = 123456789.0
        self.mock_main_app.get_remaining_disabled_seconds.return_value = 540.0  # 9 minutes

        self.popup.refresh_state()
        self.assertFalse(self.popup.master_switch.isChecked())
        self.assertIn("Paused", self.popup.lbl_title.text())
        self.assertIn("09:00", self.popup.lbl_subtitle.text())
        self.assertEqual(self.popup.btn_pause_action.text(), "Resume Now")

    def test_master_switch_actions(self):
        # Toggle off -> disables for stepper minutes
        self.popup.pause_stepper.setValue(25)
        self.popup._handle_master_toggle(False)
        self.mock_main_app.disable_for.assert_called_with(25)

        # Toggle on -> resumes
        self.popup._handle_master_toggle(True)
        self.mock_main_app.resume.assert_called_once()

    def test_relock_all_action(self):
        self.popup._handle_relock_all()
        self.mock_main_app.relock_all.assert_called_once()

    def test_quick_scan_action(self):
        self.popup._handle_quick_scan()
        self.mock_main_app.trigger_manual_auth.assert_called_with("quick_scan")

    def test_navigation_handlers(self):
        self.popup._handle_open_settings()
        self.mock_main_app.open_settings.assert_called_once()

        self.popup._handle_open_enrollment()
        self.mock_main_app.open_enrollment.assert_called_once()

        self.popup._handle_quit()
        self.mock_main_app.quit_app.assert_called_once()

    def test_show_at_tray_positioning(self):
        tray_rect = QRect(100, 10, 32, 32)
        cursor_pos = QPoint(116, 26)
        self.popup.show_at_tray(tray_rect, cursor_pos)
        self.assertTrue(self.popup.isVisible())
        self.popup.hide()
        self.assertFalse(self.popup.isVisible())


class TestFaceGateTrayIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_main_app = MagicMock()
        self.mock_main_app.is_active.return_value = True
        self.mock_main_app.disabled_until = None
        self.mock_main_app.get_protected_apps.return_value = []
        self.mock_main_app.is_app_authorized.return_value = False

        self.tray = FaceGateTray(self.mock_main_app)

    def test_tray_initialization(self):
        self.assertIsNotNone(self.tray.popup)
        self.assertIsNotNone(self.tray.menu)

    def test_tray_activation_signals(self):
        # Trigger (single click) should toggle popup
        with patch.object(self.tray, "toggle_popup") as mock_toggle:
            from PySide6.QtWidgets import QSystemTrayIcon
            self.tray._handle_activated(QSystemTrayIcon.ActivationReason.Trigger)
            mock_toggle.assert_called_once()

        # Middle click should relock all
        from PySide6.QtWidgets import QSystemTrayIcon
        self.tray._handle_activated(QSystemTrayIcon.ActivationReason.MiddleClick)
        self.mock_main_app.relock_all.assert_called_once()

    def test_launch_app_command(self):
        # String format test
        with patch("subprocess.Popen") as mock_popen, patch("shutil.which", return_value="/usr/bin/gtk-launch"):
            res = launch_app_command("firefox.desktop")
            self.assertTrue(res)
            mock_popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
