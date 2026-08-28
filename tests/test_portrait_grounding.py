"""
Verifies the portrait-specific profile association pipeline: portraits must
never be associated with nearby text based on distance alone. A heading,
section title, or unrelated narrative must be rejected even when it is the
spatially closest text block; only a region carrying real person-name
evidence (designation/biography language and adjacency only raise
confidence) may be accepted, and a portrait with no such evidence must stay
explicitly unresolved rather than borrow unrelated text as identity.

Fully generic: fixtures use made-up people/documents, never a hardcoded
roster.
"""
from src.rag.image_processor import (
    HierarchicalLayoutGrounder,
    PortraitSpatialValidator,
    SpatialDocumentContextGrounder,
)

PORTRAIT_BBOX = {"l": 50, "r": 170, "t": 700, "b": 550}  # 120x150, aspect ~0.8 -> valid portrait geometry


def _text_el(text, l, r, t, b, el_type="text", page_number=1):
    return {
        "text": text,
        "type": el_type,
        "metadata": {"bbox": {"l": l, "r": r, "t": t, "b": b}, "page_number": page_number},
    }


class TestSpatialDocumentContextGrounderRejectsNonIdentityText:
    def test_nearest_heading_is_rejected_not_associated(self):
        """
        The reported bug: a heading ("Strategic Overview") sitting right next
        to the portrait must NOT become its identity just because it is the
        closest text block.
        """
        elements = [_text_el("Strategic Overview", l=200, r=400, t=700, b=680)]
        result = SpatialDocumentContextGrounder.ground(
            image_id="img_01", bbox=PORTRAIT_BBOX, doc_elements_on_page=elements, page_number=1,
        )
        assert result["entity_name"] is None
        assert result["reason"] == "no_person_name_evidence_in_any_region"

    def test_generic_unrelated_narrative_paragraph_is_rejected(self):
        """A longer, prose-like paragraph with no name/designation must also be rejected."""
        elements = [_text_el(
            "The company continues to expand its footprint across multiple states, "
            "delivering projects on time and within budget while maintaining the highest "
            "standards of safety and quality across all sites.",
            l=200, r=400, t=700, b=650,
        )]
        result = SpatialDocumentContextGrounder.ground(
            image_id="img_02", bbox=PORTRAIT_BBOX, doc_elements_on_page=elements, page_number=1,
        )
        assert result["entity_name"] is None
        assert result["reason"] == "no_person_name_evidence_in_any_region"

    def test_no_candidate_text_at_all(self):
        result = SpatialDocumentContextGrounder.ground(
            image_id="img_03", bbox=PORTRAIT_BBOX, doc_elements_on_page=[], page_number=1,
        )
        assert result["entity_name"] is None
        assert result["reason"] == "no_candidate_regions_found"


class TestSpatialDocumentContextGrounderAcceptsRealProfileEvidence:
    def test_name_designation_and_biography_block_is_accepted(self):
        elements = [_text_el(
            "Ravi Todi, Managing Director, has over 20 years of experience in the "
            "infrastructure and EPC sector and holds an MBA in Finance.",
            l=200, r=400, t=700, b=650,
        )]
        result = SpatialDocumentContextGrounder.ground(
            image_id="img_04", bbox=PORTRAIT_BBOX, doc_elements_on_page=elements, page_number=1,
        )
        assert result["entity_name"] is not None
        assert "Ravi Todi" in result["entity_name"]
        assert result["designation"] == "Managing Director"
        assert "experience" in result["nearby_text"].lower()

    def test_confidence_scales_with_evidence_strength(self):
        """A name-only match must score lower confidence than name+designation+biography."""
        name_only = [_text_el("Mr. Ravi Todi", l=200, r=400, t=700, b=680)]
        full_evidence = [_text_el(
            "Mr. Ravi Todi, Managing Director, has over 20 years of experience in "
            "infrastructure and holds an MBA in Finance from a leading institute.",
            l=200, r=400, t=700, b=650,
        )]
        weak = SpatialDocumentContextGrounder.ground(
            image_id="img_05a", bbox=PORTRAIT_BBOX, doc_elements_on_page=name_only, page_number=1,
        )
        strong = SpatialDocumentContextGrounder.ground(
            image_id="img_05b", bbox=PORTRAIT_BBOX, doc_elements_on_page=full_evidence, page_number=1,
        )
        assert weak["entity_name"] is not None
        assert strong["entity_name"] is not None
        assert strong["confidence"] > weak["confidence"]
        # Never a flat constant regardless of content.
        assert strong["confidence"] != 0.85

    def test_grouping_merges_adjacent_name_and_designation_lines_into_one_region(self):
        """Two tightly stacked lines (name line, designation line) must be
        grouped into a single region and jointly yield the identity."""
        elements = [
            _text_el("Deepak Mehta", l=200, r=350, t=700, b=685),
            _text_el("Chief Financial Officer", l=200, r=350, t=683, b=668),
        ]
        result = SpatialDocumentContextGrounder.ground(
            image_id="img_06", bbox=PORTRAIT_BBOX, doc_elements_on_page=elements, page_number=1,
        )
        assert result["entity_name"] is not None
        assert result["designation"] == "Chief Financial Officer"


class TestSpatialDocumentContextGrounderExtendedSearch:
    def test_searches_beyond_nearest_block_when_nearest_is_not_a_profile(self):
        """
        The spatially NEAREST block is an unrelated heading; the real
        profile block sits further down the same column, beyond the normal
        search radius. The resolver must widen its search rather than
        accept the nearer heading or give up.
        """
        elements = [
            _text_el("Strategic Overview", l=200, r=400, t=700, b=680),  # nearest, no identity
            _text_el(
                "Deepak Mehta, Chief Financial Officer, has over 15 years of experience "
                "in corporate finance and treasury management.",
                l=55, r=165, t=270, b=170,  # same column as portrait, far below (gap_y=280 > 260 cap)
            ),
        ]
        result = SpatialDocumentContextGrounder.ground(
            image_id="img_07", bbox=PORTRAIT_BBOX, doc_elements_on_page=elements, page_number=1,
        )
        assert result["entity_name"] is not None
        assert "Deepak Mehta" in result["entity_name"]
        assert result["designation"] == "Chief Financial Officer"


class TestGroundImageEndToEnd:
    def test_unresolved_portrait_never_borrows_heading_as_identity(self):
        elements = [_text_el("Strategic Overview", l=200, r=400, t=700, b=680)]
        grounded = HierarchicalLayoutGrounder.ground_image(
            image_id="img_08",
            page_number=2,
            bbox=PORTRAIT_BBOX,
            doc_elements_on_page=elements,
            doc_title="Annual Report",
            active_section="Leadership",
        )
        assert grounded["association_method"] == "unresolved_portrait"
        assert grounded["entity_name"] is None
        assert grounded["designation"] is None
        assert grounded["nearby_text"] is None
        assert "strategic overview" not in (grounded["title"] or "").lower()
        assert "strategic overview" not in (grounded["caption_text"] or "").lower()
        assert grounded["association_confidence"] < 0.5

    def test_resolved_portrait_gets_evidence_based_confidence_and_nearby_text(self):
        # Placed outside PortraitSpatialValidator's tighter same_card_layout
        # window (dx > 140, dy_below not in -10..45) so this specifically
        # exercises the broader SpatialDocumentContextGrounder fallback.
        elements = [_text_el(
            "Ravi Todi, Managing Director, has over 20 years of experience in "
            "infrastructure and holds an MBA in Finance.",
            l=340, r=540, t=700, b=650,
        )]
        grounded = HierarchicalLayoutGrounder.ground_image(
            image_id="img_09",
            page_number=2,
            bbox=PORTRAIT_BBOX,
            doc_elements_on_page=elements,
            doc_title="Annual Report",
            active_section="Leadership",
        )
        assert grounded["association_method"] == "spatial_document_context"
        assert grounded["entity_name"] is not None
        assert grounded["designation"] == "Managing Director"
        assert grounded["nearby_text"] is not None
        assert "experience" in grounded["nearby_text"].lower()
        assert grounded["image_type"] == "Portrait Photo"

    def test_unresolved_portrait_not_linkable_by_entity_linker(self):
        """An unresolved portrait must never contaminate entity-based
        retrieval -- entity_linker only links chunks with a real entity_name."""
        from src.rag.entity_linker import link_entities_across_chunks

        chunks = [
            {
                "content": "Image ID: img_08\nImage Type: Portrait Photo",
                "metadata": {
                    "chunk_id": "doc1_chunk_0001",
                    "chunk_type": "image",
                    "entity_name": None,
                    "image_id": "img_08",
                },
            },
            {
                "content": "The company continues to expand its footprint across multiple states.",
                "metadata": {"chunk_id": "doc1_chunk_0002", "chunk_type": "text"},
            },
        ]
        stats = link_entities_across_chunks(chunks, "doc1")
        assert stats["portraits_linked"] == 0
        assert "entity_id" not in chunks[0]["metadata"]
        assert "entity_id" not in chunks[1]["metadata"]


class TestSameCardLayoutBiographyAttachment:
    """
    Reproduces the reported bug: a director-grid page where the portrait
    resolves via same_card_layout (name+designation matched to the card),
    but nearby_text used to fall back to the generic single-nearest
    text_before/text_after -- which picked up an unrelated heading fragment
    ("Board of...") and, in a multi-person grid, literally the NEXT
    director's own name. nearby_text must instead carry that person's own
    biography/qualifications paragraph, or stay empty -- never someone
    else's name or an unrelated heading.
    """

    MITTRA_BBOX = {"l": 40.5, "t": 638.1, "r": 134.1, "b": 538.4}  # ~93.6 x 99.7, valid portrait geometry
    BIO_TEXT = (
        "Mr. Mittra possesses a distinguished academic background and extensive "
        "industry experience exceeding 41 years. He holds a Bachelor of Engineering "
        "(Mechanical) from the Indian Institute of Technology (IIT) - Banaras Hindu "
        "University, followed by an MBA from Calcutta University."
    )

    def _elements(self):
        return [
            # Unrelated section heading, well ABOVE the matched name/designation
            # line -- must never be treated as this person's biography.
            _text_el("Board of Directors", l=40, r=300, t=680, b=660),
            # Matched name/designation line for the Mittra card.
            _text_el("Mr. Sunil Kumar Mittra, Chairman", l=140, r=300, t=635, b=615),
            # This person's own biography paragraph, directly beneath the
            # matched line, referring to him by surname only.
            _text_el(self.BIO_TEXT, l=140, r=310, t=605, b=500),
            # The NEXT director's own card (different column) -- must never
            # be absorbed as if it were Mittra's biography.
            _text_el("Mr. Ravi Todi, Managing Director", l=350, r=500, t=635, b=615),
        ]

    def test_biography_search_finds_the_right_paragraph(self):
        match = PortraitSpatialValidator.match_person_to_portrait_spatial(self.MITTRA_BBOX, self._elements())
        assert match is not None
        assert "Mittra" in match["person_name"]
        assert match["designation"] == "Chairman"
        assert match["biography_text"] == self.BIO_TEXT

    def test_ground_image_nearby_text_is_the_real_biography_not_heading_or_other_person(self):
        grounded = HierarchicalLayoutGrounder.ground_image(
            image_id="img_056",
            page_number=22,
            bbox=self.MITTRA_BBOX,
            doc_elements_on_page=self._elements(),
            active_section="Board of Directors",
        )
        assert grounded["association_method"] == "same_card_layout"
        assert "Mittra" in grounded["entity_name"]
        assert grounded["nearby_text"] == self.BIO_TEXT
        assert "board of" not in grounded["nearby_text"].lower()
        assert "ravi todi" not in grounded["nearby_text"].lower()

    def test_no_biography_paragraph_present_leaves_nearby_text_empty_not_wrong_text(self):
        """Without a real biography block on the card, nearby_text must stay
        None -- never fall back to an unrelated heading or the next card's name."""
        elements = [
            _text_el("Board of Directors", l=40, r=300, t=680, b=660),
            _text_el("Mr. Sunil Kumar Mittra, Chairman", l=140, r=300, t=635, b=615),
            _text_el("Mr. Ravi Todi, Managing Director", l=350, r=500, t=635, b=615),
        ]
        grounded = HierarchicalLayoutGrounder.ground_image(
            image_id="img_056b",
            page_number=22,
            bbox=self.MITTRA_BBOX,
            doc_elements_on_page=elements,
            active_section="Board of Directors",
        )
        assert grounded["association_method"] == "same_card_layout"
        assert grounded["nearby_text"] is None
