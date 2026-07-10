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

        import subprocess
        import os
        from database.embedding_store import get_cached_key
        from locking.launcher_sub import get_facegate_executable
        
        facegate_bin = get_facegate_executable()
        logging.info(f"Spawning recognition subprocess: {facegate_bin} --recognize {app_identifier}")
        
        cached_key = get_cached_key()
        cmd = [facegate_bin, "--recognize", app_identifier]
        pass_fds = []
        r, w = -1, -1
        if cached_key:
            r, w = os.pipe()
            os.set_inheritable(r, True)
            cmd.extend(["--key-fd", str(r)])
            pass_fds.append(r)
            
        try:
            if cached_key:
                proc = subprocess.Popen(cmd, pass_fds=pass_fds, close_fds=True)
                os.close(r)
                try:
                    os.write(w, cached_key)
                finally:
                    os.close(w)
                exit_code = proc.wait()
            else:
                proc = subprocess.Popen(cmd, close_fds=True)
                exit_code = proc.wait()
            logging.info(f"Recognition subprocess exited with code {exit_code}")
            
            success = False
            if exit_code == 0:
                success = True
            elif exit_code in (3, 4):
                # Fallback to password dialog in daemon process
                logging.info(f"Subprocess returned {exit_code}. Displaying password fallback dialog in daemon.")
                app_name = self.main_app.get_app_name(app_identifier) if self.main_app else app_identifier
                dialog = AuthDialog(app_name, mode="password")
                res = dialog.exec()
                success = (res == AuthDialog.DialogCode.Accepted)
                
            if success and self.main_app:
                self.main_app.authorize_app(app_identifier)
                
            return success
        except Exception as e:
            logging.error(f"Failed to spawn recognition subprocess: {e}. Falling back to password dialog.")
            app_name = self.main_app.get_app_name(app_identifier) if self.main_app else app_identifier
            dialog = AuthDialog(app_name, mode="password")
            res = dialog.exec()
            success = (res == AuthDialog.DialogCode.Accepted)
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
