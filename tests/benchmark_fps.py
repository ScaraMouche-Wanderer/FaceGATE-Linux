import os
import sys
import time
import cv2

# Set path to include src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from recognition.detector import Detector
from camera.camera_worker import detect_camera_device

def run_benchmark():
    print("=== Starting 30-Second FaceGate-Linux FPS Benchmark ===")
    
    # 1. Initialize detector
    print("Initializing detector...")
    detector = Detector(root_dir="models")
    print(f"Active ONNX Runtime Provider: {detector.get_provider_name()}")
    
    # 2. Open camera
    device_index = detect_camera_device()
    print(f"Opening camera device at index {device_index}...")
    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        print("Error: Could not open camera.", file=sys.stderr)
        sys.exit(1)
        
    # Configure resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    print(f"Camera Resolution: {width}x{height}")
    
    print("\nRunning face recognition inference continuously for 30 seconds...")
    start_time = time.time()
    frame_count = 0
    
    while time.time() - start_time < 30.0:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue
            
        # Run detection
        detector.detect_faces(frame)
        frame_count += 1
        
        # Print progress periodically
        elapsed = time.time() - start_time
        if frame_count % 100 == 0:
            sys.stdout.write(f"\rProcessed {frame_count} frames... ({elapsed:.1f}s elapsed, avg: {frame_count / elapsed:.2f} FPS)")
            sys.stdout.flush()
            
    total_time = time.time() - start_time
    cap.release()
    print()  # Newline after progress loop
    
    actual_fps = frame_count / total_time
    print("\n=== Benchmark Results ===")
    print(f"Total frames processed: {frame_count}")
    print(f"Total time elapsed: {total_time:.4f} seconds")
    print(f"Actual FPS: {actual_fps:.2f}")
    print(f"Camera Resolution: {int(width)}x{int(height)}")
    print(f"Active Provider: {detector.get_provider_name()}")
    print("=========================")

if __name__ == "__main__":
    run_benchmark()
