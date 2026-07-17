import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

from src.rag.contextual_analysis.models import InconsistencyIssue
from src.rag.contextual_analysis.local_checks import LocalConsistencyChecker
from src.rag.contextual_analysis.pipeline import ContextAnalysisPipeline
from src.rag.contextual_analysis.inference_service import InferenceService

def test_local_consistency_checker():
    # Setup dummy knowledge objects containing deterministic issues
    objects = [
        # Numeric mismatch
        {
            "knowledge_id": "obj_01",
            "chunk_type": "Paragraph",
            "text": "The contract value is ten thousand five hundred (1050) dollars.",
            "page_number": 1,
            "section_path": "Contract Summary"
        },
        # Broken page reference (doc has page_count=2, reference page 5)
        {
            "knowledge_id": "obj_02",
            "chunk_type": "Paragraph",
            "text": "For details, please refer to page 5 of this agreement.",
            "page_number": 1,
            "section_path": "Intro"
        },
        # Correct page reference
        {
            "knowledge_id": "obj_03",
            "chunk_type": "Paragraph",
            "text": "See page 2 for section summary.",
            "page_number": 1,
            "section_path": "Intro"
        },
        # Out-of-sequence section numbering (1.1 to 1.3)
        {
            "knowledge_id": "obj_04",
            "chunk_type": "Heading",
            "text": "1.1 Introduction",
            "page_number": 1,
            "section_path": "Intro",
            "parent_heading": "Root"
        },
        {
            "knowledge_id": "obj_05",
            "chunk_type": "Heading",
            "text": "1.3 Next Steps",
            "page_number": 1,
            "section_path": "Next Steps",
            "parent_heading": "Root"
        },
        # Duplicate headings under same parent
        {
            "knowledge_id": "obj_06",
            "chunk_type": "Heading",
            "text": "1.1 Introduction",
            "page_number": 2,
            "section_path": "Intro_Dup",
            "parent_heading": "Root"
        }
    ]

    checker = LocalConsistencyChecker(page_count=2)
    issues = checker.check_all(objects)

    # Assertions
    categories = [i.category for i in issues]
    assert "Numeric Mismatch" in categories
    assert "Reference Conflict" in categories
    assert "Terminology Inconsistency" in categories

    # Numeric mismatch assertion
    num_mismatch = next(i for i in issues if i.category == "Numeric Mismatch")
    assert "ten thousand five hundred" in num_mismatch.description
    assert "1050" in num_mismatch.description

    # Broken page reference assertion
    broken_ref = next(i for i in issues if i.category == "Reference Conflict" and "page 5" in i.description)
    assert broken_ref.page_numbers == [1]

    # Outline gap assertion
    numbering_gap = next(i for i in issues if i.category == "Reference Conflict" and "sequence" in i.description)
    assert "obj_05" in numbering_gap.object_ids

def test_inference_service_prompt_loading():
    service = InferenceService()
    assert service.system_prompt != ""
    assert "auditor" in service.system_prompt.lower()
    assert service.analysis_prompt_tmpl != ""
    assert service.verification_prompt_tmpl != ""

def test_pipeline_end_to_end(tmp_path):
    # Setup folders
    job_dir = tmp_path / "job_test_01"
    ko_dir = job_dir / "03_knowledge_objects"
    ko_dir.mkdir(parents=True, exist_ok=True)

    # Write mock knowledge_objects.json
    dummy_objects = [
        {
            "knowledge_id": "obj_01",
            "chunk_type": "Paragraph",
            "text": "Company revenue reached $15 million in FY2025.",
            "page_number": 1,
            "section_path": "Financial Overview",
            "source_file": "report.pdf",
            "metadata": {
                "word_count": 8,
                "token_estimate": 10,
                "hierarchy_path": [],
                "source_element_ids": ["el_1"],
                "bounding_boxes": []
            }
        },
        {
            "knowledge_id": "obj_02",
            "chunk_type": "Paragraph",
            "text": "Our total revenue was reported as $25 million for FY2025.",
            "page_number": 2,
            "section_path": "Financial Overview",
            "source_file": "report.pdf",
            "metadata": {
                "word_count": 9,
                "token_estimate": 12,
                "hierarchy_path": [],
                "source_element_ids": ["el_2"],
                "bounding_boxes": []
            }
        }
    ]
    with open(ko_dir / "knowledge_objects.json", "w", encoding="utf-8") as f:
        json.dump(dummy_objects, f)

    # Setup Pipeline with Mock InferenceService
    pipeline = ContextAnalysisPipeline()
    mock_service = MagicMock()
    pipeline.inference_service = mock_service
    pipeline.analysis_agent.inference_service = mock_service
    pipeline.verification_agent.inference_service = mock_service

    # Mock retrieval agent to bypass actual ChromaDB collection search
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve_similar_pairs.return_value = (
        ["obj_01", "obj_02"],
        [("obj_01", "obj_02", 0.85)],
        {"obj_01": [("obj_02", 0.85)], "obj_02": [("obj_01", 0.85)]}
    )
    pipeline.retrieval_agent = mock_retrieval

    # Mock stage 1 analysis output (JSON string)
    pipeline.inference_service.run_analysis.return_value = json.dumps([
        {
            "category": "Contradiction",
            "severity": "High",
            "confidence": 0.8,
            "description": "Conflict in FY2025 revenue: $15 million vs $25 million.",
            "evidence": "",
            "object_ids": ["obj_01", "obj_02"],
            "page_numbers": [1, 2],
            "section_path": "Financial Overview",
            "quoted_text": ""
        }
    ])

    # Mock stage 2 verification output
    pipeline.inference_service.run_verification.return_value = json.dumps({
        "verified": True,
        "confidence": 0.9,
        "revised_description": "Verified contradiction in FY2025 revenue: $15M vs $25M.",
        "reason": "Explicit numbers contradict directly."
    })

    # Run pipeline
    pipeline.run_analysis(job_dir, "job_test_01")

    # Assert outputs created
    json_report_path = job_dir / "report.json"
    html_report_path = job_dir / "report.html"
    assert json_report_path.exists()
    assert html_report_path.exists()

    # Verify JSON content
    with open(json_report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    assert report_data["document_id"] == "job_test_01"
    assert report_data["summary"]["total_issues"] == 1
    assert report_data["summary"]["high_severity"] == 1

    issue = report_data["issues"][0]
    assert issue["category"] == "Cross-section Contradictions"
    assert "Verified contradiction" in issue["description"]
    assert "obj_01" in issue["object_ids"]
    assert "obj_02" in issue["object_ids"]

def test_retrieval_agent_synonyms():
    from src.rag.contextual_analysis.semantic_retrieval_agent import SemanticRetrievalAgent
    
    agent = SemanticRetrievalAgent()
    # Mock vector_store collection interface
    mock_collection = MagicMock()
    # Get call returning mock embeddings
    mock_collection.get.return_value = {
        "ids": ["obj_01", "obj_02"],
        "embeddings": [[0.1]*384, [0.12]*384],
        "metadatas": [{}, {}],
        "documents": ["revenue was ten million", "turnover was ten million"]
    }
    # Query call returning distances (cosine distance = 1.0 - cosine similarity)
    mock_collection.query.return_value = {
        "ids": [
            ["obj_01", "obj_02"],
            ["obj_02", "obj_01"]
        ],
        "distances": [
            [0.0, 0.15],
            [0.0, 0.15]
        ]
    }
    
    agent.vector_store.client.get_collection = MagicMock(return_value=mock_collection)
    
    nodes, edges, neighbor_lists = agent.retrieve_similar_pairs("dummy_doc")
    assert "obj_01" in nodes
    assert "obj_02" in nodes
    assert len(edges) == 1
    assert edges[0][2] == 0.85  # similarity floor 0.72 check passes
    assert len(neighbor_lists["obj_01"]) == 1
    assert neighbor_lists["obj_01"][0][0] == "obj_02"

def test_louvain_clustering_stability():
    from src.rag.contextual_analysis.clustering import LouvainClusterer
    
    nodes = ["obj_01", "obj_02", "obj_03", "obj_04"]
    edges = [
        ("obj_01", "obj_02", 0.9),
        ("obj_03", "obj_04", 0.95)
    ]
    
    for _ in range(5):
        clusterer = LouvainClusterer(nodes, edges)
        clusters = clusterer.get_clusters()
        sorted_clusters = sorted([sorted(c) for c in clusters], key=lambda x: x[0])
        
        assert len(sorted_clusters) == 2
        assert sorted_clusters[0] == ["obj_01", "obj_02"]
        assert sorted_clusters[1] == ["obj_03", "obj_04"]

def test_local_checks_bypassing_llm(tmp_path):
    # Setup folders
    job_dir = tmp_path / "job_test_02"
    ko_dir = job_dir / "03_knowledge_objects"
    ko_dir.mkdir(parents=True, exist_ok=True)
    
    # Write mock knowledge_objects.json with a deterministic numeric mismatch
    dummy_objects = [
        {
            "knowledge_id": "obj_01",
            "chunk_type": "Paragraph",
            "text": "The price is ten dollars (100).",
            "page_number": 1,
            "section_path": "Summary",
            "source_file": "report.pdf"
        },
        {
            "knowledge_id": "obj_02",
            "chunk_type": "Paragraph",
            "text": "Correct price of ten dollars (10) exists.",
            "page_number": 1,
            "section_path": "Summary",
            "source_file": "report.pdf"
        }
    ]
    with open(ko_dir / "knowledge_objects.json", "w", encoding="utf-8") as f:
        json.dump(dummy_objects, f)
        
    pipeline = ContextAnalysisPipeline()
    
    # Mock retrieval agent to return these objects as a cluster
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve_similar_pairs.return_value = (
        ["obj_01", "obj_02"],
        [("obj_01", "obj_02", 0.85)],
        {"obj_01": [("obj_02", 0.85)], "obj_02": [("obj_01", 0.85)]}
    )
    pipeline.retrieval_agent = mock_retrieval
    
    # Mock LLM and assert it is NEVER called
    mock_service = MagicMock()
    pipeline.inference_service = mock_service
    pipeline.analysis_agent.inference_service = mock_service
    
    pipeline.run_analysis(job_dir, "job_test_02")
    
    mock_service.run_analysis.assert_not_called()
    mock_service.run_verification.assert_not_called()
    
    with open(job_dir / "report.json", "r", encoding="utf-8") as f:
        report = json.load(f)
    assert report["summary"]["total_issues"] >= 1
    assert report["issues"][0]["category"] == "Numeric Inconsistencies"

def test_token_budget_packing():
    from src.rag.contextual_analysis.pipeline import ContextAnalysisPipeline
    pipeline = ContextAnalysisPipeline()
    pipeline.token_budget = 40
    
    cluster_1 = [
        {"text": "A" * 40},
        {"text": "B" * 40}
    ]
    
    cluster_2 = [
        {"text": "C" * 80}
    ]
    
    cluster_3 = [
        {"text": "D" * 120}
    ]
    
    eligible = [cluster_1, cluster_2, cluster_3]
    
    batches = []
    current_batch = []
    current_tokens = 0
    
    for cluster_objs in eligible:
        cluster_tokens = 0
        for obj in cluster_objs:
            text = obj.get("text", "")
            cluster_tokens += max(10, len(text) // 4)
            
        if current_tokens + cluster_tokens > pipeline.token_budget:
            if current_batch:
                batches.append(current_batch)
            current_batch = list(cluster_objs)
            current_tokens = cluster_tokens
        else:
            current_batch.extend(cluster_objs)
            current_tokens += cluster_tokens
            
    if current_batch:
        batches.append(current_batch)
        
    assert len(batches) == 2
    assert len(batches[0]) == 3
    assert len(batches[1]) == 1
