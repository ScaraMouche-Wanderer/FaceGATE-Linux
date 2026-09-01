import os
import sys
import cv2

# Set path to include src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from recognition.detector import Detector

def test_recognition_smoke():
    print("=== Running FaceGate-Linux Recognition Smoke Test ===")
    
    # 1. Resolve paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_image_path = os.path.join(current_dir, "test_face.png")
    
    if not os.path.exists(test_image_path):
        print(f"Error: Static test face image not found at {test_image_path}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Loading static test image: {test_image_path}")
    img = cv2.imread(test_image_path)
    if img is None:
        print("Error: Failed to read image using OpenCV", file=sys.stderr)
        sys.exit(1)
        
    # 2. Initialize detector
    print("Initializing detector...")
    detector = Detector(root_dir="models")
    
    # 3. Detect faces
    print("Running face detection & embedding extraction...")
    faces = detector.detect_faces(img)
    
    # 4. Verify results
    if not faces:
        print("Error: No faces detected in the test image!", file=sys.stderr)
        sys.exit(1)
        
    print(f"Detected {len(faces)} face(s).")
    
    for idx, face in enumerate(faces):
        bbox = face['bbox']
        emb = face['embedding']
        print(f"Face {idx+1}:")
        print(f"  Bounding Box: {bbox}")
        print(f"  Embedding Shape: {emb.shape}")
        
        # Verify embedding size is 512
        assert emb.shape == (512,), f"Unexpected embedding shape: {emb.shape} (expected (512,))"
        
    print("\n=== Smoke Test Passed Successfully! ===")

if __name__ == "__main__":
    test_recognition_smoke()
