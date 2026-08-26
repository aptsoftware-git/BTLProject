import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Set root directory
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from src.rag.config import RagConfig
from src.rag.chunk_schema import DocumentChunk, ChunkMetadata
from src.rag.image_processor import ImageRetrievalValidator
from src.rag.context_builder import ContextBuilder
from src.rag.chat_service import ChatService
from src.rag.retriever import Retriever
from src.rag.retrieval_models import RetrievalOutput, ScoredChunk


class TestVisualRetrievalE2E(unittest.TestCase):
    """
    Regression test suite for end-to-end multimodal visual retrieval.
    Tests portrait retrieval, multi-person retrieval, logo retrieval, and fallback behavior.
    """

    @classmethod
    def setUpClass(cls):
        cls.doc_id = "cff0427c29e541d496d067247fba5c52"
        cls.retriever = Retriever.from_config()

    def test_01_single_person_portrait_retrieval(self):
        """Test: 'Can you show the photo of Sunil Kumar Mittra' retrieves image_146 on Page 49."""
        query = "Can you show the photo of Sunil Kumar Mittra"
        
        # 1. Intent & Target Detection
        intent = self.retriever.detect_intent(query)
        self.assertIn(intent, ("person_portrait_visual", "visual"))
        
        target_info = ImageRetrievalValidator.detect_query_target(query)
        self.assertTrue(target_info.get("is_visual"))
        self.assertEqual(target_info.get("target_type"), "portrait")
        self.assertIn("sunil", target_info.get("target_person", "").lower())
        
        # 2. Retriever Output
        retrieval_output = self.retriever.retrieve(self.doc_id, query)
        retrieved_chunks = retrieval_output.retrieved_chunks
        self.assertTrue(len(retrieved_chunks) > 0)
        
        image_chunks = [c for c in retrieved_chunks if c.metadata.chunk_type == "image"]
        self.assertTrue(len(image_chunks) > 0, "Expected at least one image chunk retrieved")
        
        sunil_chunk = image_chunks[0]
        meta = sunil_chunk.metadata
        self.assertIn("sunil", (meta.entity_name or meta.title or meta.caption or "").lower())
        self.assertEqual(meta.page_number, 49)
        self.assertTrue(ImageRetrievalValidator.validate_physical_file(image_path=meta.image_path, doc_id=self.doc_id))

        # 3. ContextBuilder & ChatService
        context_builder = ContextBuilder()
        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = (
            "Here is the portrait photograph of Mr. Sunil Kumar Mittra, Chairman.\n\n"
            "![Portrait of Mr. Sunil Kumar Mittra (Chairman)](/outputs/cff0427c29e541d496d067247fba5c52/05_images/image_146.png)\n"
            "*(Source: Page 49)*"
        )
        chat_service = ChatService(retriever=self.retriever, ollama_client=mock_ollama, context_builder=context_builder)
        response = chat_service.answer_question(self.doc_id, query)
        
        self.assertTrue(len(response.image_references) > 0)
        img_ref = response.image_references[0]
        self.assertIn("image_146.png", img_ref.get("image_url", ""))
        self.assertEqual(img_ref.get("page_number"), 49)
        self.assertIn("/outputs/cff0427c29e541d496d067247fba5c52/05_images/image_146.png", response.answer)
        self.assertNotIn("I could not find this information in the uploaded document", response.answer)

    def test_02_multi_person_portraits_retrieval(self):
        """Test: 'Show the image of Rhea Todi and Ravi Todi' retrieves both distinct portraits."""
        query = "Show the image of Rhea Todi and Ravi Todi"
        
        # 1. Target Detection
        target_info = ImageRetrievalValidator.detect_query_target(query)
        self.assertTrue(target_info.get("is_visual"))
        self.assertEqual(target_info.get("target_type"), "multi_portrait")
        target_persons = target_info.get("target_persons", [])
        self.assertTrue(any("rhea" in p for p in target_persons))
        self.assertTrue(any("ravi" in p for p in target_persons))
        
        # 2. Retriever Output
        retrieval_output = self.retriever.retrieve(self.doc_id, query)
        image_chunks = [c for c in retrieval_output.retrieved_chunks if c.metadata.chunk_type == "image"]
        self.assertTrue(len(image_chunks) >= 2, f"Expected at least 2 image chunks, got {len(image_chunks)}")
        
        retrieved_names = [(c.metadata.entity_name or c.metadata.title or "").lower() for c in image_chunks]
        self.assertTrue(any("rhea" in n for n in retrieved_names), f"Rhea Todi not found in {retrieved_names}")
        self.assertTrue(any("ravi" in n for n in retrieved_names), f"Ravi Todi not found in {retrieved_names}")
        
        # 3. Chat Service Response
        context_builder = ContextBuilder()
        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = "Here are the photos of Ms. Rhea Todi and Mr. Ravi Todi."
        chat_service = ChatService(retriever=self.retriever, ollama_client=mock_ollama, context_builder=context_builder)
        response = chat_service.answer_question(self.doc_id, query)
        
        self.assertTrue(len(response.image_references) >= 2)
        urls = [ref.get("image_url", "") for ref in response.image_references]
        self.assertTrue(any("image_148.png" in u for u in urls), f"image_148.png (Rhea Todi) not in {urls}")
        self.assertTrue(any("image_147.png" in u for u in urls), f"image_147.png (Ravi Todi) not in {urls}")
        self.assertNotIn("I could not find this information in the uploaded document", response.answer)

    def test_03_logo_retrieval(self):
        """Test: 'Show the logo of the company' retrieves company logo."""
        query = "Show the logo of the company"
        
        # 1. Target Detection
        target_info = ImageRetrievalValidator.detect_query_target(query)
        self.assertTrue(target_info.get("is_visual"))
        self.assertEqual(target_info.get("target_type"), "logo")
        
        # 2. Retriever Output
        retrieval_output = self.retriever.retrieve(self.doc_id, query)
        image_chunks = [c for c in retrieval_output.retrieved_chunks if c.metadata.chunk_type == "image"]
        self.assertTrue(len(image_chunks) > 0, "Expected at least one logo image chunk")
        
        logo_chunk = image_chunks[0]
        self.assertIn(logo_chunk.metadata.page_number, (1, 2, 3))
        self.assertTrue(ImageRetrievalValidator.validate_physical_file(image_path=logo_chunk.metadata.image_path, doc_id=self.doc_id))
        
        # 3. Chat Service Response
        context_builder = ContextBuilder()
        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = "Here is the company logo from the uploaded document."
        chat_service = ChatService(retriever=self.retriever, ollama_client=mock_ollama, context_builder=context_builder)
        response = chat_service.answer_question(self.doc_id, query)
        
        self.assertTrue(len(response.image_references) > 0)
        self.assertNotIn("I could not find this information in the uploaded document", response.answer)

    def test_04_fallback_when_no_grounded_image_exists(self):
        """Test: Query for non-existent person returns document fallback without false images."""
        query = "Can you show the photo of Elon Musk"
        
        context_builder = ContextBuilder()
        mock_ollama = MagicMock()
        mock_ollama.generate.return_value = "I could not find this information in the uploaded document."
        chat_service = ChatService(retriever=self.retriever, ollama_client=mock_ollama, context_builder=context_builder)
        response = chat_service.answer_question(self.doc_id, query)
        
        self.assertEqual(response.answer, "I could not find this information in the uploaded document.")
        self.assertEqual(len(response.image_references), 0)
        self.assertEqual(len(response.page_references), 0)


if __name__ == "__main__":
    unittest.main()
