import os
import glob
import cv2
from typing import Any
from camera.camera_worker import is_ir_frame, diagnose_camera_error

def query_v4l2_capabilities(dev_path: str) -> dict[str, Any]:
    """
    Reads hardware capabilities and metadata from Linux sysfs for a video device.
    """
    info: dict[str, Any] = {
        "name": "Unknown Camera",
        "driver": "Unknown",
        "card": "Unknown",
        "bus_info": "Unknown"
    }
    basename = os.path.basename(dev_path)
    sysfs_dir = f"/sys/class/video4linux/{basename}"
    if os.path.exists(sysfs_dir):
        name_path = os.path.join(sysfs_dir, "name")
        if os.path.exists(name_path):
            try:
                with open(name_path, "r", errors="ignore") as f:
                    info["name"] = f.read().strip()
            except Exception:
                pass
        
        index_path = os.path.join(sysfs_dir, "index")
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", errors="ignore") as f:
                    info["sysfs_index"] = f.read().strip()
            except Exception:
                pass
    return info

def get_camera_details(device_index: int) -> dict[str, Any]:
    """
    Returns full diagnostics and capabilities for a specific camera index.
    """
    from utils.platform_paths import is_linux
    dev_path = f"/dev/video{device_index}"
    sysfs_meta = query_v4l2_capabilities(dev_path) if is_linux() else {}
    
    details: dict[str, Any] = {
        "index": device_index,
        "path": dev_path if is_linux() else f"Camera {device_index}",
        "name": sysfs_meta.get("name", f"Camera Device {device_index}"),
        "working": False,
        "is_ir": False,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "error": None
    }
    
    if is_linux() and not os.path.exists(dev_path):
        details["error"] = f"Device file '{dev_path}' not found."
        return details
        
    cap = cv2.VideoCapture(device_index, cv2.CAP_V4L2) if is_linux() and hasattr(cv2, "CAP_V4L2") else cv2.VideoCapture(device_index)
    if not cap.isOpened():
        cap = cv2.VideoCapture(device_index)

        
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            details["working"] = True
            details["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            details["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            details["fps"] = cap.get(cv2.CAP_PROP_FPS)
            details["is_ir"] = is_ir_frame(frame)
        else:
            details["error"] = "Could not grab frame from video device."
        cap.release()
    else:
        details["error"] = diagnose_camera_error(device_index)
        
    return details

def enumerate_cameras(fast_scan: bool = False) -> list[dict[str, Any]]:
    """
    Enumerates video capture devices available on the system.
    Returns a list of device detail dicts.
    If fast_scan is True, queries sysfs metadata without opening cv2 capture handles.
    """
    devices: list[dict[str, Any]] = []
    video_nodes = sorted(glob.glob("/dev/video*"))
    
    indices_to_check = []
    node_map = {}
    for node in video_nodes:
        name = os.path.basename(node)
        if name.startswith("video") and name[5:].isdigit():
            idx = int(name[5:])
            indices_to_check.append(idx)
            node_map[idx] = node
            
    if not indices_to_check:
        indices_to_check = list(range(5))

    for idx in indices_to_check:
        node_path = node_map.get(idx, f"/dev/video{idx}")
        sysfs_meta = query_v4l2_capabilities(node_path)
        name = sysfs_meta.get("name", f"Camera Device {idx}")

        device_info: dict[str, Any] = {
            "index": idx,
            "path": node_path,
            "name": name,
            "working": False,
            "is_ir": False,
            "width": 0,
            "height": 0,
            "error": None
        }

        if fast_scan:
            device_info["working"] = os.path.exists(node_path) and os.access(node_path, os.R_OK)
            devices.append(device_info)
            continue

        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(idx)

        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                device_info["working"] = True
                device_info["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                device_info["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                device_info["is_ir"] = is_ir_frame(frame)
            else:
                device_info["error"] = "Failed to grab test frame"
            cap.release()
        else:
            device_info["error"] = diagnose_camera_error(idx)

        devices.append(device_info)

    return devices

def find_best_rgb_camera() -> int:
    """
    Scans devices and returns the index of the preferred RGB camera.
    """
    devices = enumerate_cameras()
    working_rgb = [d for d in devices if d["working"] and not d["is_ir"]]
    if working_rgb:
        return working_rgb[0]["index"]
    
    working_any = [d for d in devices if d["working"]]
    if working_any:
        return working_any[0]["index"]
        
    return 0

def resolve_camera_fallback(failed_index: int = 0) -> int:
    """
    Resolves a fallback camera device index if the requested index fails.
    """
    devices = enumerate_cameras()
    for dev in devices:
        if dev.get("working") and dev.get("index") != failed_index:
            return dev["index"]
    for dev in devices:
        if dev.get("working"):
            return dev["index"]
    return failed_index


def format_camera_list() -> str:
    """
    Formats the camera list as a clean CLI table string.
    """
    devices = enumerate_cameras()
    lines = [
        "📷 === Connected Video Capture Devices ===",
        f"{'IDX':<5} {'DEVICE':<14} {'TYPE':<8} {'RESOLUTION':<12} {'NAME / STATUS'}"
    ]
    lines.append("-" * 65)

    if not devices:
        lines.append("  No video capture devices found (/dev/video*).")
        return "\n".join(lines)

    for dev in devices:
        idx = str(dev['index'])
        dev_path = dev['path']
        if dev['working']:
            cam_type = "IR/Gray" if dev['is_ir'] else "RGB"
            res = f"{dev['width']}x{dev['height']}"
            status = f"\033[92m● OK\033[0m — {dev['name']}"
        else:
            cam_type = "N/A"
            res = "N/A"
            err = dev.get('error', 'Cannot open device')
            status = f"\033[91m○ ERROR\033[0m — {dev['name']} ({err})"

        lines.append(f"{idx:<5} {dev_path:<14} {cam_type:<8} {res:<12} {status}")

    lines.append("=" * 65)
    return "\n".join(lines)

