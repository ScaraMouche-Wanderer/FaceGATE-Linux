import os
import glob
import logging
import cv2
import numpy as np
from camera.camera_worker import is_ir_frame, diagnose_camera_error

def enumerate_cameras() -> list[dict]:
    """
    Enumerates video capture devices available on the system.
    Returns a list of device detail dicts.
    """
    devices = []
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
        sysfs_name_path = f"/sys/class/video4linux/video{idx}/name"
        name = f"Camera Device {idx}"
        if os.path.exists(sysfs_name_path):
            try:
                with open(sysfs_name_path, "r") as f:
                    name = f.read().strip()
            except Exception:
                pass

        device_info = {
            "index": idx,
            "path": node_path,
            "name": name,
            "working": False,
            "is_ir": False,
            "width": 0,
            "height": 0,
            "error": None
        }

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
