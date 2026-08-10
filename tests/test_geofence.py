import pytest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication

from security.geofence import GeofenceMonitor, get_current_wifi_ssid

@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app

@patch("security.geofence.subprocess.run")
def test_get_current_wifi_ssid_nmcli(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "no:other_wifi\nyes:Home_Network_5G\n"
    
    assert get_current_wifi_ssid() == "Home_Network_5G"

@patch("security.geofence.subprocess.run")
def test_get_current_wifi_ssid_iwgetid_fallback(mock_run):
    # First call to nmcli fails, second call to iwgetid succeeds
    mock_run.side_effect = [
        type("Process", (), {"returncode": 1, "stdout": ""})(),
        type("Process", (), {"returncode": 0, "stdout": "Cafe_Wifi\n"})()
    ]
    
    assert get_current_wifi_ssid() == "Cafe_Wifi"

def test_geofence_monitor_untrusted_detection(qapp):
    with patch("security.geofence.get_current_wifi_ssid") as mock_ssid:
        mock_ssid.return_value = "Home_Network"
        
        monitor = GeofenceMonitor(check_interval_sec=1)
        monitor.set_trusted_ssids(["Home_Network"], enabled=True)
        
        signals_emitted = []
        monitor.untrusted_network_detected.connect(lambda ssid: signals_emitted.append(ssid))
        
        # 1. Same network: no signal
        monitor._check_network()
        assert len(signals_emitted) == 0
        
        # 2. Transition to untrusted network: signal emitted
        mock_ssid.return_value = "Public_Cafe_Wifi"
        monitor._check_network()
        
        assert len(signals_emitted) == 1
        assert signals_emitted[0] == "Public_Cafe_Wifi"
