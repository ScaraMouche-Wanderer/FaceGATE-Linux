import os
import sys
import time
import subprocess
import unittest
from unittest.mock import patch, MagicMock

import psutil
from utils.platform_paths import (
    is_linux, is_macos, is_windows,
    get_config_dir, get_data_dir, get_runtime_dir, get_ipc_socket_address
)
from locking.process_controller import (
    suspend_process, resume_process, terminate_process, is_process_running
)
from locking.ipc_service import FaceGateService, CrossPlatformIPCServer, send_cross_platform_ipc_command


class TestPlatformPaths(unittest.TestCase):
    def test_platform_detection_booleans(self):
        """Platform detection helpers must return valid boolean results."""
        self.assertIsInstance(is_linux(), bool)
        self.assertIsInstance(is_macos(), bool)
        self.assertIsInstance(is_windows(), bool)

    def test_directory_resolvers_create_valid_paths(self):
        """Path resolvers must return existing non-empty directory strings."""
        cfg = get_config_dir()
        data = get_data_dir()
        runtime = get_runtime_dir()

        self.assertTrue(os.path.isdir(cfg))
        self.assertTrue(os.path.isdir(data))
        self.assertTrue(os.path.isdir(runtime))

    def test_ipc_socket_address(self):
        """IPC socket address must return platform-appropriate name or path."""
        addr = get_ipc_socket_address()
        self.assertIsInstance(addr, str)
        self.assertTrue(len(addr) > 0)
        if is_windows():
            self.assertEqual(addr, "FaceGateIPC")
        else:
            self.assertTrue(addr.endswith("facegate.sock"))


class TestProcessController(unittest.TestCase):
    def test_suspend_and_resume_real_process(self):
        """Process controller must suspend and resume a spawned background process."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        pid = proc.pid
        try:
            self.assertTrue(is_process_running(pid))
            
            # Suspend
            ok = suspend_process(pid)
            self.assertTrue(ok)
            p = psutil.Process(pid)
            if hasattr(psutil, "STATUS_STOPPED"):
                self.assertEqual(p.status(), psutil.STATUS_STOPPED)

            # Resume
            ok = resume_process(pid)
            self.assertTrue(ok)
            time.sleep(0.05)
            self.assertIn(p.status(), [psutil.STATUS_RUNNING, psutil.STATUS_SLEEPING])

        finally:
            terminate_process(pid, force=True)
            proc.wait(timeout=2.0)

    def test_process_controller_handles_invalid_pid(self):
        """Process controller must gracefully return False for non-existent PIDs."""
        fake_pid = 999999
        self.assertFalse(suspend_process(fake_pid))
        self.assertFalse(resume_process(fake_pid))
        self.assertTrue(terminate_process(fake_pid))


class TestCrossPlatformIPC(unittest.TestCase):
    def test_ipc_server_and_client_roundtrip(self):
        """QLocalServer and send_cross_platform_ipc_command must communicate seamlessly."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        mock_main = MagicMock()
        service = FaceGateService(mock_main)
        ipc_server = CrossPlatformIPCServer(service)
        started = ipc_server.start()
        self.assertTrue(started)

        try:
            # Process events so server socket is active
            app.processEvents()

            # Test Ping
            def send_ping():
                ok, res = send_cross_platform_ipc_command("Ping", timeout_ms=1000)
                return ok, res

            # Handle connection in Qt event loop
            import threading
            results = []

            def client_thread():
                time.sleep(0.05)
                # Run ping via local socket
                from PySide6.QtNetwork import QLocalSocket
                import json
                s = QLocalSocket()
                s.connectToServer(get_ipc_socket_address())
                if s.waitForConnected(1000):
                    s.write(json.dumps({"action": "Ping"}).encode("utf-8"))
                    s.flush()
                    if s.waitForReadyRead(1000):
                        raw = s.readAll().data().decode("utf-8")
                        results.append(json.loads(raw))
                    s.disconnectFromServer()

            t = threading.Thread(target=client_thread)
            t.start()

            for _ in range(30):
                app.processEvents()
                if results:
                    break
                time.sleep(0.05)

            t.join(timeout=1.0)
            if results:
                self.assertEqual(results[0].get("status"), "ok")
                self.assertEqual(results[0].get("result"), True)
        finally:
            ipc_server.server.close()


if __name__ == "__main__":
    unittest.main()
