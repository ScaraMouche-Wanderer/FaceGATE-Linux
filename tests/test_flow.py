import os
import sys
import time
import subprocess
import shutil

# Set path to include src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from PySide6.QtCore import QTimer, Slot, QCoreApplication, QObject, ClassInfo
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusReply, QDBusAbstractAdaptor

# Import our daemon classes
from ui.auth_dialog import AuthDialog
from locking.ipc_service import FaceGateService, FaceGateAdaptor

# Test flags
MOCK_AUTH_RESULT = True

class TestFaceGateService(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.adaptor = TestFaceGateAdaptor(self)

    def request_auth_internal(self, app_identifier: str) -> bool:
        print(f"[Test Service] Received RequestAuth for '{app_identifier}'")
        # Direct return based on mock flag, bypassing actual dialog
        return MOCK_AUTH_RESULT

@ClassInfo({"D-Bus Interface": "org.facegate.FaceGateTest"})
class TestFaceGateAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent: TestFaceGateService):
        super().__init__(parent)
        self.service = parent

    @Slot(str, result=bool)
    def RequestAuth(self, app_identifier: str) -> bool:
        return self.service.request_auth_internal(app_identifier)

def run_test():
    print("=== Starting Self-Contained D-Bus Test ===")
    
    # 1. Initialize Qt Application
    app = QCoreApplication(sys.argv)
    
    # 2. Register Test D-Bus Service
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("Error: Session D-Bus not connected.")
        sys.exit(1)
        
    service_name = "org.facegate.FaceGateTest"
    object_path = "/org/facegate/FaceGateTest"
    
    service_obj = TestFaceGateService()
    
    if not bus.registerService(service_name):
        print(f"Error: Failed to register D-Bus service '{service_name}'")
        sys.exit(1)
        
    if not bus.registerObject(object_path, service_obj):
        print(f"Error: Failed to register D-Bus object at '{object_path}'")
        sys.exit(1)
        
    print(f"Registered D-Bus service '{service_name}' at path '{object_path}'")
    
    # 3. Create Client Interface
    interface = QDBusInterface(
        service_name,
        object_path,
        service_name,
        bus
    )
    
    if not interface.isValid():
        print("Error: Client interface is invalid.")
        sys.exit(1)
        
    # We will test two scenarios:
    # Scenario A: Auth Success
    global MOCK_AUTH_RESULT
    MOCK_AUTH_RESULT = True
    print("\nScenario A: Testing Authentication Success (Expected: True)...")
    reply = QDBusReply(interface.call("RequestAuth", "kitty.desktop"))
    if not reply.isValid():
        print(f"D-Bus Call Failed: {reply.error().message()}")
        sys.exit(1)
    print(f"Result: {reply.value()} (Pass: {reply.value() == True})")
    assert reply.value() == True
    
    # Scenario B: Auth Failure
    MOCK_AUTH_RESULT = False
    print("\nScenario B: Testing Authentication Failure (Expected: False)...")
    reply = QDBusReply(interface.call("RequestAuth", "kitty.desktop"))
    if not reply.isValid():
        print(f"D-Bus Call Failed: {reply.error().message()}")
        sys.exit(1)
    print(f"Result: {reply.value()} (Pass: {reply.value() == False})")
    assert reply.value() == False
    
    print("\n=== All Integration Tests Passed! ===")
    sys.exit(0)

if __name__ == "__main__":
    run_test()
