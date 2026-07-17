import time
import psutil
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Ensure import path is set
sys.path.append(str(Path(__file__).parent))

from src.config import PipelineConfig
from src.pipeline import ProofreadingPipeline
from src.rag.contextual_analysis.pipeline import ContextAnalysisPipeline
from src.rag.multimodal_extractor import MultimodalExtractor

def get_resources():
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss / 1024 / 1024 # MB
    cpu = psutil.cpu_percent()
    return mem, cpu

def main():
    print("=== PIPELINE PROFILING RUN ===")
    test_file = Path("data/input/comprehensive_test_doc.txt")
    if not test_file.exists():
        test_file = Path("data/input/test_document.txt")
        
    print(f"Profiling file: {test_file}")
    
    stages = {}
    
    # 1. Measure Upload / Init
    t0 = time.time()
    config = PipelineConfig()
    mem, cpu = get_resources()
    stages["Initialization"] = {"time": time.time() - t0, "mem": mem, "cpu": cpu}
    
    # 2. Ingestion & Extraction (Docling / Fallback)
    t0 = time.time()
    extractor = MultimodalExtractor(enable_ocr=False, enable_table_extraction=True, enable_image_extraction=True)
    job_id = "profiling_test_run"
    job_dir = Path("data/output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    raw_text, master_doc, pages = extractor.extract(test_file, output_dir=job_dir)
    mem, cpu = get_resources()
    stages["Document Ingestion & Extraction"] = {"time": time.time() - t0, "mem": mem, "cpu": cpu}
    
    # 3. Proofreading
    t0 = time.time()
    with ProofreadingPipeline(config) as pipeline:
        result = pipeline.run(test_file, run_id=job_id)
    mem, cpu = get_resources()
    stages["Proofreading Pipeline (16 stages)"] = {"time": time.time() - t0, "mem": mem, "cpu": cpu}
    
    # 4. Contextual Consistency Analysis
    t0 = time.time()
    consistency_pipeline = ContextAnalysisPipeline()
    consistency_pipeline.run_analysis(job_dir, job_id)
    mem, cpu = get_resources()
    stages["Contextual Consistency Analysis"] = {"time": time.time() - t0, "mem": mem, "cpu": cpu}
    
    # Print Timing & Profiling Table
    print("\nPROFILING RESULTS TABLE:")
    print(f"{'Stage':<40} | {'Time (s)':<10} | {'Memory (MB)':<12} | {'CPU (%)':<8} | {'% of Total':<10}")
    print("-" * 90)
    
    total_time = sum(s["time"] for s in stages.values())
    for name, metrics in stages.items():
        pct = (metrics["time"] / total_time) * 100 if total_time > 0 else 0
        print(f"{name:<40} | {metrics['time']:<10.3f} | {metrics['mem']:<12.1f} | {metrics['cpu']:<8.1f} | {pct:<10.1f}%")
        
    print(f"Total time elapsed: {total_time:.3f} seconds")

if __name__ == "__main__":
    main()
