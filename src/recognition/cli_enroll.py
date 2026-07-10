import sys
import time
import logging
import cv2
import numpy as np

from recognition.detector import Detector
from database.embedding_store import save_embedding
from camera.camera_worker import detect_camera_device

def is_blurry(gray_frame: np.ndarray, threshold: float = 50.0) -> bool:
    """
    Check if a grayscale frame is blurry using the variance of Laplacian.
    """
    variance = cv2.Laplacian(gray_frame, cv2.CV_64F).var()
    return variance < threshold

def enroll_user(name: str):
    """
    Minimal enrollment CLI that captures sharp frames from the camera,
    extracts face embeddings, averages them, and saves the result.
    Discard raw images immediately after processing.
    """
    print(f"\n=== Enrolling user '{name}' ===")
    print("Loading face detector model...")
    detector = Detector()
    
    device_index = detect_camera_device()
    print(f"Opening camera device at index {device_index}...")
    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        print("Error: Could not open camera. Please check your connection or permissions.", file=sys.stderr)
        sys.exit(1)
        
    print("\n[INSTRUCTIONS] Please look directly at the camera.")
    print("Capturing frames...")
    
    embeddings = []
    required_frames = 15
    max_attempts = 150
    attempts = 0
    
    while len(embeddings) < required_frames and attempts < max_attempts:
        ret, frame = cap.read()
        attempts += 1
        if not ret or frame is None:
            time.sleep(0.05)
            continue
            
        # 1. Check blurriness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if is_blurry(gray):
            continue
            
        # 2. Detect face
        faces = detector.detect_faces(frame)
        if not faces:
            continue
            
        if len(faces) > 1:
            print("Warning: Multiple faces detected. Please make sure only one face is visible.")
            continue
            
        # Extract embedding
        emb = faces[0]['embedding']
        embeddings.append(emb)
        sys.stdout.write(f"\rCaptured frame {len(embeddings)}/{required_frames}...")
        sys.stdout.flush()
        
        # RAW FRAMES DISCARDED IMMEDIATELY (never written to disk)
        
        # Small delay between frames
        time.sleep(0.1)
        
    cap.release()
    print()  # Newline
    
    if len(embeddings) < required_frames:
        print(f"\nError: Could not capture enough sharp face frames. Got {len(embeddings)}/{required_frames} attempts.", file=sys.stderr)
        sys.exit(1)
        
    # Calculate average embedding
    avg_embedding = np.mean(embeddings, axis=0)
    
    # Store the averaged embedding
    save_embedding(name, avg_embedding)
    print(f"\nSUCCESS: Embedding enrolled for '{name}'.")
