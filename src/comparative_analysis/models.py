from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CompanyProfileChunk(BaseModel):
    """Represents a single semantic chunk retrieved from ChromaDB vector store."""
    chunk_id: str = Field(..., description="Unique identifier of the chunk in ChromaDB")
    text: str = Field(..., description="Content snippet of the document chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata associated with the chunk")
    page_number: Optional[int] = Field(None, description="Source page number in document")
    similarity_score: float = Field(0.0, description="Relevance or similarity score from vector query")
    query_matched: Optional[str] = Field(None, description="Predefined business query that matched this chunk")


class TargetCompanyProfile(BaseModel):
    """Raw aggregated chunk data retrieved from ChromaDB for the target company document."""
    document_id: str = Field(..., description="Unique ID / doc_hash of the indexed document")
    total_chunks: int = Field(0, description="Total number of unique chunks retrieved from ChromaDB")
    chunks: List[CompanyProfileChunk] = Field(default_factory=list, description="Retrieved semantic chunks")
    source_filename: Optional[str] = Field(None, description="Original filename of the target document")


class StrategicPartner(BaseModel):
    """Represents a strategic partner, OEM, licensor, or overseas technology provider."""
    name: str = Field(..., description="Name of the strategic partner")
    partner_type: str = Field("Technology Partner", description="Type: Technology Partner, OEM Supplier, Consortium Partner, Licensor")
    country_or_region: str = Field("Global", description="Geographic location or headquarters")
    description: str = Field("", description="Description of the partnership scope")
    strategic_value: str = Field("", description="Strategic value delivered to the target company")


class CompanyProfile(BaseModel):
    """
    Strongly typed structured profile of the uploaded company extracted and verified by Claude.
    Serves as the Single Source of Truth for all downstream agents.
    """
    company_name: str = Field("Not specified", description="Name of the company")
    company_description: str = Field("Not specified", description="Detailed company overview")
    executive_summary: str = Field("Not specified", description="Compact 150-250 word grounded executive summary")
    primary_industry: str = Field("Not specified", description="Primary industry sector")
    secondary_industries: List[str] = Field(default_factory=list, description="Secondary or related industry sectors")
    core_services: List[str] = Field(default_factory=list, description="Core services offered")
    products: List[str] = Field(default_factory=list, description="Products or software offerings")
    business_domains: List[str] = Field(default_factory=list, description="Business verticals or domains")
    major_projects: List[str] = Field(default_factory=list, description="Major projects or case studies")
    technologies: List[str] = Field(default_factory=list, description="Technologies, frameworks, or tools used")
    geographic_presence: List[str] = Field(default_factory=list, description="Geographic regions or countries served")
    target_industries: List[str] = Field(default_factory=list, description="Target customer industries")
    key_clients: List[str] = Field(default_factory=list, description="Key clients or customer logos")
    business_strengths: List[str] = Field(default_factory=list, description="Core business strengths")
    competitive_advantages: List[str] = Field(default_factory=list, description="Key competitive advantages")
    keywords: List[str] = Field(default_factory=list, description="Relevant business keywords")
    certifications: List[str] = Field(default_factory=list, description="Certifications and compliance standards")
    strategic_partners: List[StrategicPartner] = Field(default_factory=list, description="Strategic partners, licensors, OEMs, and technology providers")

    @property
    def industry(self) -> str:
        """Backward compatible industry property."""
        return self.primary_industry if self.primary_industry != "Not specified" else "Not specified"


# Legacy alias for backward compatibility
CompanySummary = CompanyProfile


class SearchQuery(BaseModel):
    """Query object generated for competitor discovery and web research."""
    query: str = Field(..., description="Search query string")
    purpose: str = Field(..., description="Objective of the query")
    category: str = Field("competitor_search", description="Category tag")


class SearchQueryBatch(BaseModel):
    """Container for a set of generated search queries."""
    company_name: str = Field(..., description="Target company name")
    primary_industry: str = Field(..., description="Target primary industry")
    queries: List[SearchQuery] = Field(default_factory=list, description="Generated search queries")


class TavilySearchResult(BaseModel):
    """Single search result item returned from Tavily Web Search API."""
    title: str = Field("", description="Title of the web page")
    url: str = Field("", description="URL of the web page")
    snippet: str = Field("", description="Search snippet")
    content: str = Field("", description="Body content of snippet")
    score: float = Field(0.0, description="Relevance score from search engine")
    company_name: str = Field("Not specified", description="Extracted company name associated with URL")
    website: str = Field("", description="Clean domain / official website URL")
    query_ref: Optional[str] = Field(None, description="Query that produced this result")


class CompetitorRawData(BaseModel):
    """Raw search results aggregated for a specific candidate competitor."""
    competitor_name: str = Field(..., description="Identified competitor name")
    official_website: str = Field("", description="Official website URL")
    search_results: List[TavilySearchResult] = Field(default_factory=list, description="Associated search snippets")
    source_urls: List[str] = Field(default_factory=list, description="List of source URLs")


class CompetitorProfile(BaseModel):
    """Structured profile of a competitor synthesized by Claude from Tavily search data."""
    company_name: str = Field(..., description="Name of the competitor")
    industry: str = Field("Not specified", description="Primary industry sector")
    company_description: str = Field("Not specified", description="Detailed company overview")
    executive_summary: str = Field("Not specified", description="Compact grounded summary")
    core_services: List[str] = Field(default_factory=list, description="Core services or offerings")
    products: List[str] = Field(default_factory=list, description="Products or software offerings")
    business_domains: List[str] = Field(default_factory=list, description="Primary business domains")
    major_projects: List[str] = Field(default_factory=list, description="Major projects or case studies")
    technologies: List[str] = Field(default_factory=list, description="Technologies or capabilities used")
    geographic_presence: List[str] = Field(default_factory=list, description="Geographic footprint or headquarters")
    business_strengths: List[str] = Field(default_factory=list, description="Core business strengths")
    competitive_advantages: List[str] = Field(default_factory=list, description="Key competitive advantages")
    official_website: str = Field("Not specified", description="Official website URL")
    source_urls: List[str] = Field(default_factory=list, description="Tavily source URLs used")
    references: List[str] = Field(default_factory=list, description="Source references")

    # Backward compatibility properties
    @property
    def name(self) -> str:
        return self.company_name

    @property
    def website(self) -> str:
        return self.official_website

    @property
    def overview(self) -> str:
        return self.executive_summary


class CompetitorSummaryList(BaseModel):
    """Collection of structured competitor profiles and industry benchmark summary."""
    industry: str = Field("Not specified", description="Target industry")
    competitors: List[CompetitorProfile] = Field(default_factory=list, description="List of competitor profiles")
    industry_overview: str = Field("", description="Synthesized view of overall industry competitive dynamics")


class FeatureComparisonRow(BaseModel):
    """Matrix row comparing target company against competitors for a specific dimension."""
    dimension: str = Field(..., description="Feature, capability, or strategic dimension")
    target_company_score: str = Field(..., description="Target company status or capability description")
    competitor_scores: Dict[str, str] = Field(default_factory=dict, description="Competitor name to status/capability mapping")
    insights: str = Field("", description="Key observation or takeaway")


class CapabilityGap(BaseModel):
    """Identified capability gap where competitors offer capabilities absent in target company."""
    category: str = Field(..., description="Category tag: Service, Technology, Market, Geographic, Product")
    gap_title: str = Field(..., description="Title of the identified gap")
    description: str = Field(..., description="Detailed description of missing capability")
    offered_by_competitors: List[str] = Field(default_factory=list, description="Competitors providing this capability")
    business_risk: str = Field("Medium", description="Business risk level: High, Medium, Low")


class GapAnalysis(BaseModel):
    """Structured output of Gap Analysis Agent."""
    service_gaps: List[CapabilityGap] = Field(default_factory=list, description="Services competitors provide but target company does not")
    technology_gaps: List[CapabilityGap] = Field(default_factory=list, description="Technologies competitors use that are absent")
    market_gaps: List[CapabilityGap] = Field(default_factory=list, description="Industries competitors serve that are not covered")
    geographic_gaps: List[CapabilityGap] = Field(default_factory=list, description="Geographic markets competitors operate in that are not covered")
    product_gaps: List[CapabilityGap] = Field(default_factory=list, description="Product categories competitors offer that are missing")
    summary: str = Field("", description="High-level narrative of critical gaps")


class CompanyStrengthItem(BaseModel):
    """Identified area where target company is stronger than market competitors."""
    title: str = Field(..., description="Title of the competitive strength")
    description: str = Field(..., description="Detailed description of advantage")
    advantage_type: str = Field(..., description="Type: Domain Expertise, Technology Moat, Service Depth, Positioning")
    key_differentiator: str = Field("", description="Key differentiator vs market peers")


class IndustrySnapshot(BaseModel):
    """Structured synthesis of broader industry patterns across competitors and web intelligence."""
    common_industry_trends: List[str] = Field(default_factory=list, description="Dominant macro trends across peers")
    frequently_offered_services: List[str] = Field(default_factory=list, description="Core baseline services offered by competitors")
    emerging_technologies: List[str] = Field(default_factory=list, description="Emerging technologies being adopted")
    frequently_targeted_segments: List[str] = Field(default_factory=list, description="Primary customer verticals targeted")
    common_project_types: List[str] = Field(default_factory=list, description="Standard project scopes across competitors")
    common_certifications: List[str] = Field(default_factory=list, description="Baseline certifications in this sector")
    geographic_expansion_patterns: List[str] = Field(default_factory=list, description="Primary export / expansion regions")
    industry_summary: str = Field("", description="Executive summary of market dynamics")


class MarketPosition(BaseModel):
    """Qualitative classification of target company's market standing (No numerical scores)."""
    classification: str = Field(..., description="Classification: Industry Leader | Strong Competitor | Emerging Competitor | Niche Specialist | Specialized Provider")
    position_title: str = Field(..., description="Descriptive headline of company positioning")
    supporting_evidence: List[str] = Field(default_factory=list, description="Concrete evidence points supporting classification")
    competitive_moat: str = Field("", description="Primary moat protecting market standing")
    market_tier_rationale: str = Field("", description="Strategic rationale for position placement")


class CompetitiveDifferentiator(BaseModel):
    """What makes this company different from market peers."""
    title: str = Field(..., description="Title of differentiator")
    category: str = Field(..., description="Category: Specialized Expertise, Unique Technology, Niche Focus, Execution Capability, Service Portfolio")
    description: str = Field(..., description="Detailed description of distinction")
    supporting_evidence: str = Field(..., description="Evidence comparing target company against competitors")


class SWOTComparison(BaseModel):
    """Comparative SWOT analysis comparing target company against competitors."""
    strengths_vs_competitors: List[str] = Field(default_factory=list, description="Strengths relative to competitors")
    weaknesses_vs_competitors: List[str] = Field(default_factory=list, description="Weaknesses relative to competitors")
    opportunities_in_market: List[str] = Field(default_factory=list, description="Market opportunities unexploited by competitors")
    threats_from_competitors: List[str] = Field(default_factory=list, description="Competitive threats and market risks")


class CategorizedOpportunity(BaseModel):
    """Categorized market growth opportunity referencing competitor evidence and trends."""
    id: str = Field(..., description="Unique ID (e.g. OPP-001)")
    title: str = Field(..., description="Opportunity title")
    category: str = Field(..., description="Category: Technology | Market Expansion | Service Expansion | Digital Transformation | Geographic Expansion | Strategic Partnerships")
    description: str = Field(..., description="Detailed description")
    competitor_evidence: str = Field(..., description="Specific competitor evidence")
    industry_trend_reference: str = Field(..., description="Associated Tavily industry trend")
    supporting_observation: str = Field(..., description="Supporting internal or market observation")


# Alias for backward compatibility
InnovationOpportunity = CategorizedOpportunity


class ExecutiveInsights(BaseModel):
    """High-level decision-support insights synthesized by Claude."""
    top_strengths: List[str] = Field(default_factory=list, description="Top 3-5 company strengths")
    top_weaknesses: List[str] = Field(default_factory=list, description="Top 3-5 company weaknesses")
    top_risks: List[str] = Field(default_factory=list, description="Top 3-5 business risks")
    top_growth_opportunities: List[str] = Field(default_factory=list, description="Top 3-5 growth opportunities")
    key_competitive_threats: List[str] = Field(default_factory=list, description="Top competitive threats from peers")
    most_promising_expansion_areas: List[str] = Field(default_factory=list, description="Most promising expansion areas")
    executive_summary_narrative: str = Field("", description="Comprehensive executive decision-support narrative")


class ComparativeAnalysisResult(BaseModel):
    """Synthesized head-to-head comparative analysis results and matrix."""
    target_company_name: str = Field(..., description="Target company name")
    industry: str = Field(..., description="Industry sector")
    feature_matrix: List[FeatureComparisonRow] = Field(default_factory=list, description="Feature comparison matrix")
    swot_analysis: SWOTComparison = Field(default_factory=SWOTComparison, description="Comparative SWOT analysis")
    market_positioning_score: float = Field(0.0, description="Overall comparative standing score")
    key_differentiators: List[str] = Field(default_factory=list, description="Key factors distinguishing target company")
    comparative_summary: str = Field("", description="Detailed narrative comparing company to industry peers")


class CompetitorSelectionReason(BaseModel):
    """Why a specific competitor was selected for benchmarking (Transparency)."""
    competitor_name: str = Field(..., description="Name of the competitor")
    industry_match_score: int = Field(90, description="Industry match percentage 0-100%")
    service_match_score: int = Field(85, description="Service offerings match percentage 0-100%")
    market_match_score: int = Field(80, description="Customer segment / market match percentage 0-100%")
    geographic_match_score: int = Field(75, description="Geographic footprint match percentage 0-100%")
    overall_match_score: int = Field(85, description="Overall match score percentage 0-100%")
    rationale: str = Field("", description="Justification for selection")


class EvidenceSWOTItem(BaseModel):
    """Evidence-backed SWOT item with source traceability."""
    statement: str = Field(..., description="SWOT statement")
    evidence: str = Field("", description="Supporting document or market benchmark evidence")
    source: str = Field("Annual Report / Source Document", description="Source document or reference")
    confidence: int = Field(90, description="Confidence score 0-100%")


class EnhancedSWOT(BaseModel):
    """Evidence-grounded SWOT analysis."""
    strengths: List[EvidenceSWOTItem] = Field(default_factory=list)
    weaknesses: List[EvidenceSWOTItem] = Field(default_factory=list)
    opportunities: List[EvidenceSWOTItem] = Field(default_factory=list)
    threats: List[EvidenceSWOTItem] = Field(default_factory=list)


class ScoredMatrixRow(BaseModel):
    """0-10 numerical scoring row comparing target company against competitors."""
    capability: str = Field(..., description="Capability or dimension (e.g. EPC Execution, Bulk Material Handling)")
    target_company_score: int = Field(8, description="Target company score 0-10")
    competitor_scores: Dict[str, int] = Field(default_factory=dict, description="Competitor name to 0-10 score mapping")
    evidence_rationale: str = Field("", description="Grounding evidence rationale")


class ConfidenceScores(BaseModel):
    """Global confidence framework scores across all comparative analysis sections."""
    profile_confidence: int = Field(95, description="Company profile extraction confidence %")
    competitor_confidence: int = Field(87, description="Competitor selection & validation confidence %")
    swot_confidence: int = Field(89, description="SWOT analysis confidence %")
    recommendation_confidence: int = Field(91, description="Strategic recommendations confidence %")


class ExecutiveVisualizations(BaseModel):
    """Data structures for executive-friendly visual charts."""
    positioning_map: List[Dict[str, Any]] = Field(default_factory=list, description="Positioning map items (x_market_presence, y_capability_depth)")
    swot_summary_counts: Dict[str, int] = Field(default_factory=dict, description="Counts of Strengths, Weaknesses, Opportunities, Threats")
    radar_chart: Dict[str, Dict[str, int]] = Field(default_factory=dict, description="Capability dimension to company scores (0-10)")


class StrategicRecommendation(BaseModel):
    """Prioritized strategic recommendation generated by Claude."""
    id: str = Field(..., description="Unique recommendation ID (e.g. REC-001)")
    observation: str = Field("", description="Key observation derived from competitor benchmarking")
    supporting_evidence: str = Field("", description="Supporting competitor evidence or web observation")
    business_impact: str = Field("", description="Anticipated business outcome / financial impact")
    suggested_action: str = Field("", description="Actionable step-by-step strategic recommendation")
    title: str = Field("", description="Concise recommendation title")
    rationale: str = Field("", description="Why this recommendation is suggested")
    expected_impact: str = Field("", description="Anticipated business outcome")
    priority: str = Field("High", description="Priority level: High, Medium, Low")
    category: str = Field("Strategic Growth", description="Category tag")
    action_items: List[str] = Field(default_factory=list, description="Step-by-step execution items")
    source_references: List[str] = Field(default_factory=list, description="Source references (e.g. Annual Report, Market Benchmark Dataset)")
    confidence_score: int = Field(90, description="Confidence score 0-100%")


class ComparativeAnalysisRequest(BaseModel):
    """API Request payload to trigger Comparative Analysis on an indexed document."""
    document_id: str = Field(..., description="Unique document identifier already indexed in ChromaDB")
    target_company_name: Optional[str] = Field(None, description="Optional override for target company name")
    industry_override: Optional[str] = Field(None, description="Optional override for target industry")
    custom_competitor_names: Optional[List[str]] = Field(None, description="Optional list of specific competitors")
    max_competitors: int = Field(5, description="Maximum number of competitors to evaluate")


class ComparativeAnalysisResponse(BaseModel):
    """API Response containing complete Phase 5 Executive Decision-Support System outputs."""
    analysis_id: str = Field(..., description="Unique comparative analysis execution ID")
    document_id: str = Field(..., description="Indexed document ID evaluated")
    status: str = Field("completed", description="Execution status: pending, in_progress, completed, failed")
    company_profile: Optional[CompanyProfile] = Field(None, description="Synthesized target company profile verified by Claude")
    competitor_profiles: Optional[CompetitorSummaryList] = Field(None, description="Synthesized competitor profiles from Tavily")
    industry_snapshot: Optional[IndustrySnapshot] = Field(None, description="Industry intelligence snapshot across peers")
    market_position: Optional[MarketPosition] = Field(None, description="Qualitative market position classification")
    competitive_differentiators: List[CompetitiveDifferentiator] = Field(default_factory=list, description="Evidence-backed company differentiators")
    comparative_analysis: Optional[ComparativeAnalysisResult] = Field(None, description="Comparative benchmark matrix")
    gap_analysis: Optional[GapAnalysis] = Field(None, description="Service, Tech, Market, Geo, and Product Gaps")
    company_strengths: List[CompanyStrengthItem] = Field(default_factory=list, description="Core competitive advantages over peers")
    categorized_opportunities: List[CategorizedOpportunity] = Field(default_factory=list, description="Categorized business growth opportunities")
    executive_insights: Optional[ExecutiveInsights] = Field(None, description="Claude executive insights and risk/growth analysis")
    strategic_recommendations: List[StrategicRecommendation] = Field(default_factory=list, description="Prioritized recommendations by Claude")
    strategic_partnerships: List[StrategicPartner] = Field(default_factory=list, description="Strategic partners, licensors, and OEMs")
    competitor_selection_reasons: List[CompetitorSelectionReason] = Field(default_factory=list, description="Transparency breakdown for competitor selection")
    scored_comparison_matrix: List[ScoredMatrixRow] = Field(default_factory=list, description="Scoring-based 0-10 comparison matrix")
    confidence_scores: Optional[ConfidenceScores] = Field(None, description="Confidence scores across report sections")
    executive_visualizations: Optional[ExecutiveVisualizations] = Field(None, description="Executive visual components (positioning map, radar chart, swot summary)")
    enhanced_swot: Optional[EnhancedSWOT] = Field(None, description="Evidence-backed SWOT framework")
    report_paths: Dict[str, str] = Field(default_factory=dict, description="File paths for generated reports")
    execution_time_seconds: float = Field(0.0, description="Total execution duration in seconds")
    error: Optional[str] = Field(None, description="Error message if execution failed")

    @property
    def innovation_opportunities(self) -> List[CategorizedOpportunity]:
        return self.categorized_opportunities
