import os
# Limit ONNX Runtime and math library threads to prevent CPU spikes and thermal throttling
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import time
import logging
import numpy as np
import onnxruntime
from insightface.app import FaceAnalysis

class Detector:
    def __init__(self, model_name: str = "buffalo_l", root_dir: str = "models"):
        self.model_name = model_name
        self.root_dir = root_dir
        
        # Determine execution providers (prefer GPU acceleration if present)
        available_providers = onnxruntime.get_available_providers()
        logging.info(f"Available ONNX Runtime providers: {available_providers}")
        
        providers = []
        if "CUDAExecutionProvider" in available_providers:
            providers.append("CUDAExecutionProvider")
        if "ROCmExecutionProvider" in available_providers:
            providers.append("ROCmExecutionProvider")
        providers.append("CPUExecutionProvider")
        
        self.provider = providers[0]
        logging.info(f"Selected ONNX Runtime provider: {self.provider}")
        
        # Load FaceAnalysis model
        start_time = time.perf_counter()
        self.app = FaceAnalysis(name=self.model_name, root=self.root_dir, providers=providers)
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        self.load_time = time.perf_counter() - start_time
        logging.info(f"buffalo_l models initialized in {self.load_time:.4f} seconds.")

    def get_provider_name(self) -> str:
        return self.provider

    def get_load_time(self) -> float:
        return self.load_time

    def detect_faces(self, frame: np.ndarray):
        """
        Detects faces in a BGR frame.
        
        Returns:
            List of dictionaries containing:
                - 'bbox': [x1, y1, x2, y2]
                - 'embedding': np.ndarray (size 512)
                - 'kps': keypoints
        """
        try:
            faces = self.app.get(frame)
            results = []
            for face in faces:
                results.append({
                    'bbox': face.bbox.astype(int).tolist(),
                    'embedding': face.embedding,
                    'kps': face.kps
                })
            return results
        except Exception as e:
            logging.error(f"Error in face detection: {e}")
            return []
