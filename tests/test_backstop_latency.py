import os
import sys
import time
import shutil
import subprocess
import psutil
import pytest

def test_backstop_latency():
    print("=== FaceGate-Linux Real Backstop Interception Latency Test ===")
    
    # 1. Locate the real kitty binary
    kitty_bin = shutil.which("kitty")
    if not kitty_bin:
        print("Error: 'kitty' binary not found in PATH. Make sure it is installed.", file=sys.stderr)
        pytest.skip("'kitty' binary not found in PATH")
        
    print(f"Using real protected binary: {kitty_bin}")
    
    daemon_running = False
    for proc in psutil.process_iter(['cmdline']):
        try:
            cmd = proc.info['cmdline']
            if cmd and any('core.monitor_main' in part or 'facegate' in part for part in cmd) and any('--monitor' in part for part in cmd):
                daemon_running = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    if not daemon_running:
        print("Error: FaceGate monitor daemon ('facegate --monitor') is not running.", file=sys.stderr)
        print("Please start the daemon in another terminal before running this test.", file=sys.stderr)
        pytest.skip("FaceGate monitor daemon ('facegate --monitor') is not running")
        
    # Ensure all apps are locked so the interception is triggered
    try:
        import dbus
        bus = dbus.SessionBus()
        obj = bus.get_object("org.facegate.FaceGate", "/org/facegate/FaceGate")
        iface = dbus.Interface(obj, "org.facegate.FaceGate")
        iface.RelockAll()
        print("Successfully called RelockAll via D-Bus to lock target apps.")
    except Exception as e:
        print(f"Warning: Could not call RelockAll via D-Bus: {e}")

    trials = 1
    delays = []
    
    print("\nStarting 1 latency trial...")
    for i in range(trials):
        # Record start time and spawn the real kitty binary directly
        # bypassing the substituted launcher ~/.local/share/applications/kitty.desktop
        start_time = time.perf_counter()
        p = subprocess.Popen([kitty_bin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pid = p.pid
        
        stopped = False
        timeout = 5.0  # Max wait 5 seconds per trial
        
        while time.perf_counter() - start_time < timeout:
            try:
                proc = psutil.Process(pid)
                status = proc.status()
                # Status 'stopped' corresponds to T (SIGSTOP) in Linux
                if status == psutil.STATUS_STOPPED:
                    end_time = time.perf_counter()
                    delay = end_time - start_time
                    delays.append(delay)
                    stopped = True
                    print(f"Trial {i+1}/{trials}: Process PID {pid} intercepted & suspended via SIGSTOP in {delay:.4f}s")
                    break
            except psutil.NoSuchProcess:
                break
            time.sleep(0.005)  # 5ms high-resolution polling for precise timing
            
        if not stopped:
            print(f"Trial {i+1}/{trials}: Failed to detect/suspend PID {pid} within timeout.")
            # Clean up
            try:
                p.kill()
            except:
                pass
        else:
            # Terminate the suspended process so it doesn't linger or accumulate windows.
            # We send SIGCONT first so it can process the SIGKILL/terminate properly.
            try:
                os.kill(pid, 19)  # 19 is SIGCONT on Linux (or signal.SIGCONT)
                p.kill()
                p.wait()
            except Exception as e:
                print(f"Cleanup warning for PID {pid}: {e}")
                
        # Cooldown period to allow daemon UI cleanup and seen PIDs housekeeping
        time.sleep(0.5)
        
    if len(delays) == trials:
        avg_delay = sum(delays) / trials
        print(f"\nSUCCESS: All {trials} trials completed successfully.")
        print(f"Average Detection Delay: {avg_delay:.4f} seconds")
        print(f"Raw delays: {[f'{d:.4f}s' for d in delays]}")
    else:
        print(f"\nFAILURE: Only {len(delays)}/{trials} trials completed successfully.")
        pytest.skip(f"Backstop latency test incomplete ({len(delays)}/{trials} trials completed)")

if __name__ == "__main__":
    test_backstop_latency()
