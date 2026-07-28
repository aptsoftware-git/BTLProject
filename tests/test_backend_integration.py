from __future__ import annotations

import json
import unittest
import asyncio
import httpx

from backend.app import app
from backend.services import get_job_dir


class TestBackendIntegration(unittest.TestCase):

    def setUp(self):
        self.test_job_id = "test_integration_job_999"
        self.job_dir = get_job_dir(self.test_job_id)
        self.job_dir.mkdir(parents=True, exist_ok=True)

        comp_dir = self.job_dir / "comparative_analysis"
        comp_dir.mkdir(parents=True, exist_ok=True)

        company_profile = {"company_name": "Vertexa Inc.", "primary_industry": "AI & Document Intelligence"}
        competitor_profiles = {"competitors": [{"name": "Abbyy Software", "industry": "AI & Document Intelligence"}]}
        comparison_matrix = {"feature_matrix": [{"dimension": "Industry", "target_company_val": "AI & Document Intelligence"}]}
        gap_analysis = {"service_gaps": [{"gap_title": "Enterprise Cloud API", "description": "Cloud API deployment", "category": "Technology", "business_risk": "Medium"}]}
        swot_analysis = {"strengths_vs_competitors": ["Proprietary LLM Verification"]}
        recommendations = [{"title": "Deploy Enterprise Cloud API", "observation": "Obs", "supporting_evidence": "Ev", "business_impact": "Imp", "suggested_action": "Act"}]
        comparative_report = {
            "company_profile": company_profile,
            "competitors": competitor_profiles,
            "comparative_matrix": comparison_matrix,
            "gap_analysis": gap_analysis,
            "swot_analysis": swot_analysis,
            "recommendations": recommendations
        }

        with open(comp_dir / "company_profile.json", "w", encoding="utf-8") as f:
            json.dump(company_profile, f)
        with open(comp_dir / "competitor_profiles.json", "w", encoding="utf-8") as f:
            json.dump(competitor_profiles, f)
        with open(comp_dir / "comparison_matrix.json", "w", encoding="utf-8") as f:
            json.dump(comparison_matrix, f)
        with open(comp_dir / "gap_analysis.json", "w", encoding="utf-8") as f:
            json.dump(gap_analysis, f)
        with open(comp_dir / "swot_analysis.json", "w", encoding="utf-8") as f:
            json.dump(swot_analysis, f)
        with open(comp_dir / "recommendations.json", "w", encoding="utf-8") as f:
            json.dump(recommendations, f)
        with open(comp_dir / "comparative_report.json", "w", encoding="utf-8") as f:
            json.dump(comparative_report, f)
        with open(comp_dir / "comparative_report.html", "w", encoding="utf-8") as f:
            f.write("<html><body>Comparative Report</body></html>")
        with open(comp_dir / "executive_dashboard.html", "w", encoding="utf-8") as f:
            f.write("<html><body>Executive Dashboard</body></html>")

        job_data = {
            "job_id": self.test_job_id,
            "filename": "Vertexa_Mini_Company_Handbook.pdf",
            "status": "completed",
            "current_stage": "Completed",
            "progress_percentage": 100.0,
            "created_at": "2026-07-27T12:00:00",
            "completed_at": "2026-07-27T12:05:00",
            "error": None,
            "file_path": str(self.job_dir / "Vertexa_Mini_Company_Handbook.pdf"),
            "result": {"total_issues": 0}
        }
        with open(self.job_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(job_data, f)

    def test_comparative_analysis_endpoints(self):
        async def run_test():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                res = await client.get(f"/api/reports/{self.test_job_id}/comparative-analysis")
                self.assertEqual(res.status_code, 200)
                self.assertIn("company_profile", res.json()["data"])

                res = await client.get(f"/api/reports/{self.test_job_id}/company-profile")
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["data"]["company_name"], "Vertexa Inc.")

                res = await client.get(f"/api/reports/{self.test_job_id}/competitor-profiles")
                self.assertEqual(res.status_code, 200)
                self.assertEqual(len(res.json()["data"]["competitors"]), 1)

                res = await client.get(f"/api/reports/{self.test_job_id}/comparison-matrix")
                self.assertEqual(res.status_code, 200)
                self.assertIn("feature_matrix", res.json()["data"])

                res = await client.get(f"/api/reports/{self.test_job_id}/swot")
                self.assertEqual(res.status_code, 200)
                self.assertIn("strengths_vs_competitors", res.json()["data"])

                res = await client.get(f"/api/reports/{self.test_job_id}/recommendations")
                self.assertEqual(res.status_code, 200)
                self.assertEqual(len(res.json()["data"]), 1)

        asyncio.run(run_test())

    def test_file_downloads(self):
        async def run_test():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                res = await client.get(f"/api/download/{self.test_job_id}/comparative_report.html")
                self.assertEqual(res.status_code, 200)
                self.assertIn("Comparative Report", res.text)

                res = await client.get(f"/api/download/{self.test_job_id}/executive_dashboard.html")
                self.assertEqual(res.status_code, 200)
                self.assertIn("Executive Dashboard", res.text)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
