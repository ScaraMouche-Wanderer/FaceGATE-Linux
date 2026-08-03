import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="module")
def qt_app():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_auth_queue_serialization(qt_app):
    """Verifies handle_monitor_auth queues multiple requests and processes them sequentially."""
    from core.monitor_main import FaceGateApplication

    config = {
        "protected_apps": [
            {"id": "app1", "desktop_name": "app1.desktop"},
            {"id": "app2", "desktop_name": "app2.desktop"},
        ],
        "behavior.launcher_recheck_interval_minutes": 0,
        "app_monitor.poll_interval_seconds": 1.5,
    }

    processed_order = []

    def mock_process_auth_request(desktop_name, pid):
        processed_order.append((desktop_name, pid))

    with patch("core.monitor_main.register_dbus_service", return_value=True), \
         patch("locking.launcher_manager.get_launcher_manager"), \
         patch("core.monitor_main.apply_substitution"), \
         patch("locking.app_monitor.AppMonitor.start"), \
         patch.object(FaceGateApplication, "check_tray_and_start"), \
         patch.object(FaceGateApplication, "_process_auth_request", side_effect=mock_process_auth_request):

        app = FaceGateApplication(config)

        # Trigger rapid consecutive auth requests
        app.handle_monitor_auth("app1.desktop", 1001)
        app.handle_monitor_auth("app2.desktop", 1002)

        # Pump Qt event loop iterations to process singleShot(0, self._process_auth_queue)
        for _ in range(5):
            QCoreApplication.processEvents()

        # Both requests should be processed in exact FIFO order
        assert processed_order == [("app1.desktop", 1001), ("app2.desktop", 1002)]
        assert len(app._auth_queue) == 0
        assert app._auth_busy is False
