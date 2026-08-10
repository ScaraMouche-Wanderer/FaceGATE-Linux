"""
D-Bus IPC integration test for FaceGate.
Uses a mock service on a test bus name to verify the RequestAuth
round-trip without requiring the actual daemon.

Updated post-security-audit: EmergencyKill now requires authentication,
so the mock service reflects the new behavior.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from PySide6.QtCore import QTimer, Slot, QCoreApplication, QObject, ClassInfo
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusReply, QDBusAbstractAdaptor


# Test flags
MOCK_AUTH_RESULT = True


class MockFaceGateService(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.adaptor = MockFaceGateAdaptor(self)
        self.auth_call_count = 0

    def request_auth_internal(self, app_identifier: str) -> bool:
        self.auth_call_count += 1
        print(f"[Test Service] Received RequestAuth for '{app_identifier}' (call #{self.auth_call_count})")
        return MOCK_AUTH_RESULT


@ClassInfo({"D-Bus Interface": "org.facegate.FaceGateTest"})
class MockFaceGateAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent: MockFaceGateService):
        super().__init__(parent)
        self.service = parent

    @Slot(str, result=bool)
    def RequestAuth(self, app_identifier: str) -> bool:
        return self.service.request_auth_internal(app_identifier)

    @Slot(str, dict, result=bool)
    def RequestAuthWithEnv(self, app_identifier: str, env: dict) -> bool:
        return self.service.request_auth_internal(app_identifier)


def run_test():
    print("=== Starting D-Bus IPC Integration Test ===")

    # 1. Initialize Qt Application
    app = QCoreApplication(sys.argv)

    # 2. Register Test D-Bus Service
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("Error: Session D-Bus not connected.")
        sys.exit(1)

    service_name = "org.facegate.FaceGateTest"
    object_path = "/org/facegate/FaceGateTest"

    service_obj = MockFaceGateService()

    if not bus.registerService(service_name):
        print(f"Error: Failed to register D-Bus service '{service_name}'")
        sys.exit(1)

    if not bus.registerObject(object_path, service_obj):
        print(f"Error: Failed to register D-Bus object at '{object_path}'")
        sys.exit(1)

    print(f"Registered D-Bus service '{service_name}' at path '{object_path}'")

    # 3. Create Client Interface
    interface = QDBusInterface(service_name, object_path, service_name, bus)

    if not interface.isValid():
        print("Error: Client interface is invalid.")
        sys.exit(1)

    # --- Scenario A: Auth Success ---
    global MOCK_AUTH_RESULT
    MOCK_AUTH_RESULT = True
    print("\nScenario A: Testing Authentication Success (Expected: True)...")
    reply = QDBusReply(interface.call("RequestAuth", "kitty.desktop"))
    if not reply.isValid():
        print(f"D-Bus Call Failed: {reply.error().message()}")
        sys.exit(1)
    print(f"Result: {reply.value()} (Pass: {reply.value() == True})")
    assert reply.value() == True, f"Expected True, got {reply.value()}"

    # --- Scenario A2: RequestAuthWithEnv Success ---
    print("\nScenario A2: Testing RequestAuthWithEnv Success (Expected: True)...")
    from PySide6.QtDBus import QDBus
    reply_env = QDBusReply(interface.callWithArgumentList(QDBus.CallMode.Block, "RequestAuthWithEnv", ["kitty.desktop", {"DISPLAY": ":0"}]))
    if not reply_env.isValid():
        print(f"D-Bus Call Failed: {reply_env.error().message()}")
        sys.exit(1)
    assert reply_env.value() == True

    # --- Scenario B: Auth Failure ---
    MOCK_AUTH_RESULT = False
    print("\nScenario B: Testing Authentication Failure (Expected: False)...")
    reply = QDBusReply(interface.call("RequestAuth", "kitty.desktop"))
    if not reply.isValid():
        print(f"D-Bus Call Failed: {reply.error().message()}")
        sys.exit(1)
    print(f"Result: {reply.value()} (Pass: {reply.value() == False})")
    assert reply.value() == False, f"Expected False, got {reply.value()}"

    # --- Scenario C: Multiple rapid calls ---
    MOCK_AUTH_RESULT = True
    print("\nScenario C: Testing rapid sequential calls (5x)...")
    for i in range(5):
        reply = QDBusReply(interface.call("RequestAuth", f"app_{i}.desktop"))
        assert reply.isValid(), f"Call {i} failed: {reply.error().message()}"
        assert reply.value() == True

    assert service_obj.auth_call_count == 8, \
        f"Expected 8 total auth calls, got {service_obj.auth_call_count}"
    print(f"Total auth calls processed: {service_obj.auth_call_count} ✓")

    print("\n=== All D-Bus Integration Tests Passed! ===")
    sys.exit(0)


if __name__ == "__main__":
    run_test()
