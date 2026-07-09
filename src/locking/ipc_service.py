import logging
from PySide6.QtCore import QObject, Slot, ClassInfo
from PySide6.QtDBus import QDBusConnection, QDBusAbstractAdaptor
from ui.auth_dialog import AuthDialog

class FaceGateService(QObject):
    def __init__(self, main_app=None):
        super().__init__()
        self.main_app = main_app
        # Instantiate the adaptor to map this QObject to the D-Bus interface
        self.adaptor = FaceGateAdaptor(self)

    def request_auth_internal(self, app_identifier: str) -> bool:
        logging.info(f"D-Bus request received: RequestAuth for '{app_identifier}'")
        
        # If the monitor is currently disabled, bypass auth
        if self.main_app and not self.main_app.is_active():
            logging.info("FaceGate is inactive/disabled. Auto-authorizing.")
            return True

        # Lookup user-friendly name from main application
        app_name = app_identifier
        if self.main_app:
            app_name = self.main_app.get_app_name(app_identifier)
            
        # Create and execute the dialog modally
        dialog = AuthDialog(app_name)
        result = dialog.exec()
        
        success = (result == AuthDialog.DialogCode.Accepted)
        logging.info(f"Authentication result for '{app_identifier}': {success}")
        
        # Notify the main app to update process states if necessary
        if success and self.main_app:
            self.main_app.authorize_app(app_identifier)
            
        return success

@ClassInfo({"D-Bus Interface": "org.facegate.FaceGate"})
class FaceGateAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent: FaceGateService):
        super().__init__(parent)
        self.service = parent

    @Slot(str, result=bool)
    def RequestAuth(self, app_identifier: str) -> bool:
        return self.service.request_auth_internal(app_identifier)

def register_dbus_service(service_obj) -> bool:
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        logging.error("Failed to connect to Session D-Bus.")
        return False
        
    if not bus.registerService("org.facegate.FaceGate"):
        logging.error("Failed to register D-Bus service name: org.facegate.FaceGate. Is FaceGate already running?")
        return False
        
    if not bus.registerObject("/org/facegate/FaceGate", service_obj):
        logging.error("Failed to register object at path: /org/facegate/FaceGate")
        return False
        
    logging.info("D-Bus service 'org.facegate.FaceGate' registered successfully.")
    return True
