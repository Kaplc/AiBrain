import hashlib
import numpy as np
import threading
import logging

logger = logging.getLogger(__name__)

# Global model handle
_model = None
_model_name = None


def get_model_name():
    """Get the currently configured model name."""
    from .config import settings
    return settings.embedding_model


def get_embedding_dim():
    """Get the embedding dimension for the current model."""
    from .config import settings
    return settings.embedding_dim


def _load_model_with_timeout(timeout_seconds: float = 3.0):
    """Try to load the sentence transformer model with a timeout."""
    import os
    # Skip model loading if offline mode
    if os.environ.get('HF_HUB_OFFLINE') == '1':
        logger.info("HF_HUB_OFFLINE=1, skipping model loading")
        return None

    result = {"model": None, "error": None}

    def load():
        try:
            from sentence_transformers import SentenceTransformer
            model_name = get_model_name()
            logger.info(f"Loading sentence-transformers model: {model_name}")
            result["model"] = SentenceTransformer(model_name)
            result["error"] = None
        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"Failed to load sentence-transformers: {e}")

    thread = threading.Thread(target=load, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        logger.warning(f"Model loading timed out after {timeout_seconds}s")
        return None

    return result["model"]


def load_sentence_transformer():
    """Try to load sentence transformer model, return None on failure."""
    global _model, _model_name

    if _model is not None:
        return _model

    model_name = get_model_name()
    logger.info(f"Attempting to load model: {model_name}")

    model = _load_model_with_timeout(timeout_seconds=120.0)

    if model is not None:
        _model = model
        _model_name = model_name
        logger.info("Sentence transformer loaded successfully")
        return _model

    # Fallback to hash-based embeddings
    logger.warning("No model available - will use hash-based fallback embeddings")
    return None


def encode_texts(texts: list[str]) -> list[list[float]]:
    """Encode texts to embeddings, with fallback to hash-based if model unavailable."""

    model = load_sentence_transformer()

    if model is not None:
        try:
            embeddings = model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        except Exception as e:
            logger.warning(f"Model encoding failed: {e}, using fallback")

    # Fallback: use hash-based pseudo-embeddings for demo purposes
    logger.info("Using hash-based fallback embeddings")
    return hash_embed(texts, dim=get_embedding_dim())


def hash_embed(texts: list[str], dim: int = 384) -> list[list[float]]:
    """Create deterministic pseudo-embeddings from text hash.

    This is a fallback for demo purposes when no model is available.
    It produces consistent embeddings but without semantic meaning.
    """
    embeddings = []
    for text in texts:
        # Create multiple hash-based features
        features = []
        for n in [2, 3, 4]:  # character n-grams
            for i in range(len(text) - n + 1):
                ngram = text[i:i+n]
                h = int(hashlib.md5(ngram.encode()).hexdigest()[:8], 16)
                features.append(h % 1000)

        # Make consistent length
        while len(features) < dim:
            h = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
            features.extend([(h >> (i * 8)) & 0xFF for i in range(min(8, dim - len(features)))])

        # Normalize
        vec = np.array(features[:dim], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        embeddings.append(vec.tolist())

    return embeddings
