from abc import ABC, abstractmethod
from typing import List

class EmbeddingProvider(ABC):
    """
    Abstract Base Class for modular embedding providers.
    """
    
    @abstractmethod
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates dense vector embeddings for a list of text strings.
        """
        pass

class SentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider utilizing the sentence-transformers library.
    """
    
    def __init__(self, model_name: str, device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    @property
    def model(self):
        """Lazy load the model on first use to conserve memory/startup time."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            # Load the model on the specified device
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        
        # sentence-transformers encode method generates embeddings
        # convert_to_numpy=True returns numpy array, we convert to list of floats
        embeddings_numpy = self.model.encode(
            texts, 
            batch_size=32, 
            show_progress_bar=False, 
            convert_to_numpy=True
        )
        return embeddings_numpy.tolist()
