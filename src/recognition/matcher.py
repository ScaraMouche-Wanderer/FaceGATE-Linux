import numpy as np
import logging
from database.embedding_store import load_embeddings
from utils.config_loader import get_config

def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    dot_product = np.dot(emb1, emb2)
    norm1 = np.linalg.norm(emb1)
    norm2 = np.linalg.norm(emb2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_product / (norm1 * norm2))

def match_face(live_embedding: np.ndarray) -> tuple:
    """
    Matches a live face embedding against enrolled embeddings.
    
    Returns:
        (matched_name, confidence) if a successful match is found, or (None, confidence)
    """
    config = get_config()
    threshold = float(config.get("recognition.similarity_threshold", 0.65))
    ambiguity_margin = float(config.get("recognition.ambiguity_margin", 0.03))
    
    enrolled = load_embeddings()
    if not enrolled:
        logging.warning("No enrolled embeddings found.")
        return None, 0.0
        
    scores = []
    for name, stored_emb in enrolled.items():
        sim = cosine_similarity(live_embedding, stored_emb)
        scores.append((name, sim))
        
    if not scores:
        return None, 0.0
        
    # Sort scores by similarity in descending order
    scores.sort(key=lambda x: x[1], reverse=True)
    
    top_name, top_score = scores[0]
    logging.info(f"Top match candidate: '{top_name}' with similarity: {top_score:.4f}")
    
    # Check for ambiguity if multiple candidates are enrolled
    if len(scores) > 1:
        second_name, second_score = scores[1]
        margin = top_score - second_score
        if margin < ambiguity_margin and top_score >= threshold:
            logging.warning(
                f"Match rejected due to ambiguity: top candidate '{top_name}' ({top_score:.4f}) "
                f"is too close to second candidate '{second_name}' ({second_score:.4f}) with margin {margin:.4f} "
                f"(required margin: {ambiguity_margin})"
            )
            return None, top_score
            
    if top_score >= threshold:
        logging.info(f"Successful match: '{top_name}' (similarity: {top_score:.4f} >= threshold: {threshold})")
        return top_name, top_score
        
    logging.info(f"No match found: similarity {top_score:.4f} is below threshold {threshold}")
    return None, top_score
