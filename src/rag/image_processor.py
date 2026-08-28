import logging
import re
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple
from src.rag.document_schema import ImageMetadata
from src.rag.utils import convert_bbox
from src.rag.caption_processor import CaptionProcessor

logger = logging.getLogger("pipeline")

# Generic corporate designations recognised regardless of who holds them --
# NOT tied to any specific named person. Used to ground a person's
# name+designation for ANY portrait directly from real document text
# (explicit caption or nearby OCR), so portrait metadata isn't limited to a
# hardcoded roster.
_KNOWN_DESIGNATIONS = [
    "Managing Director", "Executive Director", "Independent Director",
    "Whole-time Director", "Whole time Director", "Non-Executive Director",
    "Additional Director", "Nominee Director", "Alternate Director",
    "Vice Chairman", "Vice Chairperson", "Chairman", "Chairperson",
    "Chief Executive Officer", "CEO", "Chief Financial Officer", "CFO",
    "Chief Operating Officer", "COO", "Chief Technology Officer", "CTO",
    "Company Secretary", "President", "Vice President", "General Manager",
    "Founder", "Co-Founder", "Promoter", "Director",
]
_DESIGNATION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(d) for d in sorted(_KNOWN_DESIGNATIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
# First word of every designation phrase -- excluded from name-token capture
# so e.g. "Dr. Alok Banerjee Chief Technology Officer" stops the name at
# "Banerjee" instead of swallowing "Chief Technology" into the person's name.
_DESIGNATION_LEAD_WORDS = {d.split()[0].lower() for d in _KNOWN_DESIGNATIONS}
_NAME_TOKEN = rf"(?!(?i:{'|'.join(re.escape(w) for w in _DESIGNATION_LEAD_WORDS)})\b)[A-Z][a-zA-Z.'\-]+"
_TITLE_PREFIX = r"(?:Mr|Mrs|Ms|Dr|Shri|Smt|Er)\.?\s+"
# "Mr. Sunil Kumar Mittra" / "Shri Ravi Todi" / "Dr. A. K. Sharma"
_NAMED_PERSON_PATTERN = re.compile(
    rf"\b(?:{_TITLE_PREFIX})({_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}})"
)


def extract_generic_person_identity(text: Optional[str]) -> Optional[Tuple[str, Optional[str]]]:
    """
    Generic (non-hardcoded) extraction of a person's name + designation from
    real document text (an explicit Docling caption, or OCR text lifted from
    near an image). Only fires on a titled name (Mr./Ms./Dr./Shri/Smt./Er.)
    so it never mistakes an arbitrary capitalized phrase for a person, and
    only reports a designation when one of a fixed set of real corporate
    titles is present nearby -- it never invents one.

    Returns (name, designation_or_None) or None if no confident person
    reference is found.
    """
    if not text or not text.strip():
        return None
    clean = re.sub(r"\s+", " ", text.strip())

    name_match = _NAMED_PERSON_PATTERN.search(clean)
    if not name_match:
        return None
    name = f"{clean[max(0, name_match.start()):name_match.end()]}".strip()
    # Re-include the title prefix as matched (group 0 covers prefix+name).
    name = re.sub(r"\s+", " ", name)

    designation = None
    tail = clean[name_match.end():name_match.end() + 60]
    desig_match = _DESIGNATION_PATTERN.search(tail) or _DESIGNATION_PATTERN.search(clean)
    if desig_match:
        designation = desig_match.group(1)

    return name, designation


# A bare 2-4 word Title-Case run, no honorific required -- deliberately looser
# than _NAMED_PERSON_PATTERN, so it is only ever used gated on a real
# _KNOWN_DESIGNATIONS match immediately adjacent (see
# extract_untitled_name_near_designation below), which is what keeps it from
# matching an arbitrary capitalized phrase.
_BARE_NAME_TOKEN = rf"(?!(?i:{'|'.join(re.escape(w) for w in _DESIGNATION_LEAD_WORDS)})\b)[A-Z][a-zA-Z.'\-]+"
_BARE_NAME_PATTERN = re.compile(rf"\b({_BARE_NAME_TOKEN}(?:\s+{_BARE_NAME_TOKEN}){{1,3}})\b")


def extract_untitled_name_near_designation(text: Optional[str]) -> Optional[Tuple[str, Optional[str]]]:
    """
    Catches a person's name printed directly under/beside their photo with no
    honorific -- the common "Name" / "Role" caption pattern under a portrait
    (e.g. printed_text transcribed by a VLM from the pixels themselves, a
    literal reading of real document content, not a model guess). Unlike
    extract_generic_person_identity, this does not require Mr./Ms./Dr. --
    but it only ever fires when a real corporate designation from
    _KNOWN_DESIGNATIONS is found immediately next to the name, so it can't
    mistake an arbitrary capitalized phrase (a section heading, a place name)
    for a person -- the designation match is the anchor of trust, same
    principle as extract_generic_person_identity's honorific requirement.

    The name search is windowed tightly around the designation match (not
    the whole input), so a name+designation label immediately followed by a
    longer bio/description paragraph (common under a portrait on a
    leadership/director page) still resolves correctly -- only the
    proximity to the designation is trusted, not the overall text length.
    """
    if not text or not text.strip():
        return None
    clean = re.sub(r"\s+", " ", text.strip())

    desig_match = _DESIGNATION_PATTERN.search(clean)
    if not desig_match:
        return None

    _WINDOW = 60
    before = clean[max(0, desig_match.start() - _WINDOW):desig_match.start()]
    after = clean[desig_match.end():desig_match.end() + _WINDOW]

    name_match = None
    for candidate_text, from_end in ((before, True), (after, False)):
        m = None
        for m in _BARE_NAME_PATTERN.finditer(candidate_text):
            pass  # take the last match before the designation, or first match after it
        if from_end:
            name_match = m
        else:
            name_match = _BARE_NAME_PATTERN.search(candidate_text)
        if name_match:
            break

    if not name_match:
        return None

    name = re.sub(r"\s+", " ", name_match.group(1)).strip()
    return name, desig_match.group(1)


# Generic legal-entity suffixes -- these are ordinary English/corporate-law
# vocabulary (not any specific company's name), used purely to recognise
# WHERE a real organization name sits inside real nearby text.
_ORG_SUFFIX_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,'\-\s]{1,60}?\s+"
    r"(?:Limited|Ltd\.?|LLC|LLP|Inc\.?|Incorporated|Corporation|Corp\.?|"
    r"Pvt\.?\s*Ltd\.?|Private\s+Limited|PLC|Co\.?|Company|Group|Enterprises))\b"
)


def extract_generic_organization_name(text_candidates: List[Optional[str]]) -> Optional[str]:
    """
    Generic (non-hardcoded) extraction of an organization/company name from
    real document text, by matching a real legal-entity suffix (Limited,
    Ltd, LLC, Pvt Ltd, Corporation, ...) actually present in the text --
    never a fixed company name. Returns the first match found across the
    given candidate texts, in order.
    """
    for text in text_candidates:
        if not text or not text.strip():
            continue
        m = _ORG_SUFFIX_PATTERN.search(text)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


class PortraitSpatialValidator:
    """
    Validates portrait geometry and pairs images with people using strict 1-to-1 spatial layout analysis.
    Rejects collages, logos, decorative banners, industrial scenes, and unrelated photos.

    Fully generic: a person's identity is derived directly from real nearby
    document text -- a titled name (extract_generic_person_identity) or an
    untitled name printed beside a real corporate designation
    (extract_untitled_name_near_designation) -- never from a fixed roster of
    names, so this works identically for any document's own directors/staff.
    """

    @staticmethod
    def validate_portrait_geometry(
        bbox: Optional[Any] = None,
        width: Optional[float] = None,
        height: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Evaluates whether bounding box / image dimensions fit an individual portrait photograph.
        Rejects horizontal banners, full-page graphics, tiny icons, and wide landscape scenes.
        """
        w, h = width, height
        if bbox:
            if isinstance(bbox, dict):
                l = bbox.get("l", 0)
                r = bbox.get("r", 0)
                t = bbox.get("t", 0)
                b = bbox.get("b", 0)
            else:
                l = getattr(bbox, "l", 0)
                r = getattr(bbox, "r", 0)
                t = getattr(bbox, "t", 0)
                b = getattr(bbox, "b", 0)
            w = abs(r - l) if (w is None or w <= 0) else w
            h = abs(t - b) if (h is None or h <= 0) else h

        if not w or not h or w <= 0 or h <= 0:
            return False, "Missing or invalid dimensions"

        # Aspect ratio W / H
        aspect = w / h

        # Rejection rules
        if aspect > 1.28:
            return False, f"Landscape or banner aspect ratio ({aspect:.2f} > 1.28)"
        if aspect < 0.68:
            return False, f"Extremely tall or vertical strip aspect ratio ({aspect:.2f} < 0.68)"
        if w < 40 or h < 40:
            return False, f"Too small for individual portrait ({w:.0f}x{h:.0f} < 40x40 pt)"
        if w > 300 or h > 320:
            return False, f"Too large for individual portrait ({w:.0f}x{h:.0f} > 300x320 pt)"

        return True, f"Valid portrait geometry ({w:.1f}x{h:.1f} pt, aspect {aspect:.2f})"

    @staticmethod
    def match_person_to_portrait_spatial(
        image_bbox: Any,
        text_elements_on_page: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Finds a 1-to-1 spatial match between an image and a nearby name/designation
        on the same page. The candidate name is extracted directly from each
        nearby text block's own content (generic, real-text-only extraction) --
        never looked up against a fixed roster -- so this works for any person
        actually named beside the image in the document.
        """
        # First check geometry
        is_geom, reason = PortraitSpatialValidator.validate_portrait_geometry(image_bbox)
        if not is_geom:
            return None

        if isinstance(image_bbox, dict):
            il, ir, it, ib = image_bbox.get("l", 0), image_bbox.get("r", 0), image_bbox.get("t", 0), image_bbox.get("b", 0)
        else:
            il = getattr(image_bbox, "l", 0)
            ir = getattr(image_bbox, "r", 0)
            it = getattr(image_bbox, "t", 0)
            ib = getattr(image_bbox, "b", 0)

        icx = (il + ir) / 2.0
        icy = (it + ib) / 2.0

        best_match = None
        best_dist = 999999.0

        for txt_el in text_elements_on_page:
            t_text = (txt_el.get("text") or "").strip()
            if not t_text:
                continue

            tbox = txt_el.get("metadata", {}).get("bbox") or txt_el.get("bbox") or {}
            if isinstance(tbox, dict):
                tl, tr, tt, tb = tbox.get("l", 0), tbox.get("r", 0), tbox.get("t", 0), tbox.get("b", 0)
            else:
                tl = getattr(tbox, "l", 0)
                tr = getattr(tbox, "r", 0)
                tt = getattr(tbox, "t", 0)
                tb = getattr(tbox, "b", 0)

            tcx = (tl + tr) / 2.0
            tcy = (tt + tb) / 2.0

            # Extract identity directly from this nearby text block's own
            # content -- a titled name, or an untitled name beside a real
            # corporate designation. No fixed roster involved.
            identity = extract_generic_person_identity(t_text) or extract_untitled_name_near_designation(t_text)
            if not identity:
                continue
            name, designation = identity

            # Check horizontal adjacency: text box is to the right of image
            dx = tl - ir
            dy_top = abs(it - tt)
            dy_center = abs(icy - tcy)

            # Check vertical adjacency: text box is directly below image
            dy_below = ib - tt
            dx_center = abs(icx - tcx)

            # Horizontal match (standard multi-column portrait directory layout)
            if -15 <= dx <= 140 and (dy_top <= 30 or dy_center <= 55):
                dist = dx * 0.5 + dy_top * 1.5
                if dist < best_dist:
                    best_dist = dist
                    best_match = {
                        "person_name": name,
                        "designation": designation,
                        "layout_alignment": "horizontal",
                        "distance_pt": dist,
                        "caption_text": f"Portrait of {name} ({designation})" if designation else f"Portrait of {name}",
                        "matched_text": t_text,
                        "matched_bbox": (tl, tr, tt, tb),
                    }

            # Vertical match (single column stacked portrait layout)
            elif -10 <= dy_below <= 45 and dx_center <= 45:
                dist = dy_below * 1.0 + dx_center * 1.0
                if dist < best_dist:
                    best_dist = dist
                    best_match = {
                        "person_name": name,
                        "designation": designation,
                        "layout_alignment": "vertical",
                        "distance_pt": dist,
                        "caption_text": f"Portrait of {name} ({designation})" if designation else f"Portrait of {name}",
                        "matched_text": t_text,
                        "matched_bbox": (tl, tr, tt, tb),
                    }

        if best_match:
            best_match["biography_text"] = PortraitSpatialValidator._find_biography_text_for_card(
                matched_bbox=best_match["matched_bbox"],
                matched_name=best_match["person_name"],
                text_elements_on_page=text_elements_on_page,
            )

        return best_match

    @staticmethod
    def _find_biography_text_for_card(
        matched_bbox: Tuple[float, float, float, float],
        matched_name: str,
        text_elements_on_page: List[Dict[str, Any]],
        max_gap: float = 70.0,
    ) -> Optional[str]:
        """
        Once a person's name/designation line has been matched to a
        portrait's own card, this looks for the biography/qualifications
        paragraph that actually belongs to THAT card -- the text block
        stacked immediately below the matched name/designation line, in the
        same column, close enough to be part of the same card. Explicitly
        rejects a candidate that itself names a DIFFERENT person (the
        adjacent card's own name/title line in a multi-person directory
        grid), so one person's card never absorbs a neighboring person's
        name as if it were their biography.
        """
        mtl, mtr, mtt, mtb = matched_bbox

        # Token-overlap comparison (not substring containment): a biography
        # paragraph often refers to the person by surname only ("Mr. Mittra"
        # for "Mr. Sunil Kumar Mittra"), which is NOT a contiguous substring
        # match but clearly the same person -- while "Ravi Todi" sharing no
        # token at all with "Sunil Kumar Mittra" is clearly a different one.
        _STOP_NAME_WORDS = {"mr", "mrs", "ms", "dr", "shri", "smt", "er"}

        def _name_tokens(s: Optional[str]) -> set:
            cleaned = re.sub(r"[^a-z\s]", " ", (s or "").lower())
            return {w for w in cleaned.split() if len(w) > 2 and w not in _STOP_NAME_WORDS}

        matched_tokens = _name_tokens(matched_name)
        best_bio = None
        best_gap = max_gap + 1.0

        for txt_el in text_elements_on_page:
            t_text = (txt_el.get("text") or "").strip()
            if not t_text or t_text == matched_name or len(t_text) < 15:
                continue
            tbox = txt_el.get("metadata", {}).get("bbox") or txt_el.get("bbox") or {}
            tl, tr, tt, tb = _get_bbox_coords(tbox)
            if tl == 0 and tr == 0 and tt == 0 and tb == 0:
                continue

            gap = mtb - tt  # positive: this block starts below the matched line
            h_overlap = max(0.0, min(mtr, tr) - max(mtl, tl))
            same_column = h_overlap > 0 or abs(mtl - tl) < 40.0
            if not (0.0 <= gap <= max_gap and same_column):
                continue

            # Reject a block that itself names a DIFFERENT person (shares no
            # name token at all with the matched person) -- an adjacent
            # card's own name/designation line, not this card's bio. A
            # surname-only mention of the SAME person is allowed through.
            other_identity = extract_generic_person_identity(t_text) or extract_untitled_name_near_designation(t_text)
            if other_identity:
                other_tokens = _name_tokens(other_identity[0])
                if other_tokens and matched_tokens and not (other_tokens & matched_tokens):
                    continue

            if gap < best_gap:
                best_gap = gap
                best_bio = t_text

        return best_bio


def _get_bbox_coords(box: Any) -> Tuple[float, float, float, float]:
    if isinstance(box, dict):
        return (
            float(box.get("l", 0) or 0),
            float(box.get("r", 0) or 0),
            float(box.get("t", 0) or 0),
            float(box.get("b", 0) or 0),
        )
    return (
        float(getattr(box, "l", 0) or 0),
        float(getattr(box, "r", 0) or 0),
        float(getattr(box, "t", 0) or 0),
        float(getattr(box, "b", 0) or 0),
    )


_BIO_NARRATIVE_CUES = re.compile(
    r"\b(?:has|holds|graduated|joined|leads|leading|responsible|overseeing|oversees|manages|"
    r"specializ\w*|years of experience|experience in|expertise in|career|serves as|serving as|"
    r"previously|prior to|instrumental in|qualified|qualification|alumnus|alumna)\b",
    re.IGNORECASE,
)


def _looks_like_biography_text(text: str) -> bool:
    """
    Generic (content-based, never name-specific) signal that a block of text
    reads like narrative biography/profile prose rather than a heading,
    section title, or unrelated short caption -- length plus common
    biography-narrative vocabulary. Deliberately weak on its own: never
    sufficient by itself to assign identity (a generic company-history
    paragraph can also "sound biographical"), only used to raise confidence
    once a real name has already been found in the same region.
    """
    words = text.split()
    if len(words) < 10:
        return False
    return bool(_BIO_NARRATIVE_CUES.search(text))


class SpatialDocumentContextGrounder:
    """
    Portrait-specific profile association: pairs a portrait's bounding box
    with the correct nearby PERSON-PROFILE region on the same page -- never
    just "whatever text happens to be closest" (a heading like "Strategic
    Overview" or an unrelated narrative paragraph must never be treated as
    portrait identity context, no matter how spatially close it is).

    Pipeline:
      1. Detect all text blocks around the portrait on the page (geometry:
         horizontal/vertical distance, vertical overlap ratio, column
         adjacency, reading order).
      2. Group adjacent candidate blocks into logical profile/content
         regions (a name line + a designation line + a biography paragraph
         stacked/aligned together read as one region, the way a real
         profile card is laid out) using layout + reading-order adjacency.
      3. Score every region on actual identity evidence -- a real person
         name, a real designation/title, biography-narrative language, and
         its spatial adjacency to the portrait -- never on distance alone.
      4. Only a region that clears the evidence bar (a name must be found;
         designation/biography evidence and adjacency only add confidence)
         is accepted. If nothing in the normal search radius clears the
         bar, the search is widened (larger distance cap, and the full
         same-column span regardless of distance) before giving up.
      5. If no region ever clears the bar, the portrait is left explicitly
         UNRESOLVED -- entity_name/designation/nearby_text/confidence are
         never populated from a heading or unrelated narrative just because
         it was nearby.
    """

    # Maximum spatial distance (PDF points) for the normal search pass.
    MAX_ASSOCIATION_DISTANCE = 260.0
    # Widened distance cap used only on the extended ("search beyond the
    # immediate nearest block") pass, when the normal pass found no region
    # with real identity evidence.
    EXTENDED_ASSOCIATION_DISTANCE = MAX_ASSOCIATION_DISTANCE * 3.0
    # Blocks that share the portrait's own column are searched the full
    # page height on the extended pass (a directory column can place the
    # matching name/designation well below the immediate nearest line).
    MAX_REGION_GAP = 42.0  # PDF points -- max gap between two blocks to merge them into one region

    @staticmethod
    def _candidate_blocks(
        image_bbox_coords: Tuple[float, float, float, float],
        doc_elements_on_page: List[Dict[str, Any]],
        extended: bool = False,
    ) -> List[Dict[str, Any]]:
        il, ir, it, ib = image_bbox_coords
        i_height = max(1e-6, it - ib)
        i_width = max(1e-6, ir - il)
        candidates: List[Dict[str, Any]] = []
        distance_cap = (
            SpatialDocumentContextGrounder.EXTENDED_ASSOCIATION_DISTANCE
            if extended else SpatialDocumentContextGrounder.MAX_ASSOCIATION_DISTANCE
        )

        for order_idx, el in enumerate(doc_elements_on_page):
            t_str = (el.get("text") or "").strip()
            el_type = (el.get("type") or "").lower()
            if not t_str or el_type in ("image", "pictureitem", "imageitem"):
                continue
            t_box = el.get("metadata", {}).get("bbox") or el.get("bbox") or {}
            tl, tr, tt, tb = _get_bbox_coords(t_box)
            if tl == 0 and tr == 0 and tt == 0 and tb == 0:
                continue
            t_height = max(1e-6, tt - tb)

            # Horizontal / vertical gaps (0 when the boxes overlap on that axis)
            gap_x = max(0.0, tl - ir, il - tr)
            gap_y = max(0.0, tb - it, ib - tt)

            # Vertical overlap: how much of the text block's height sits in
            # the same horizontal "row band" as the portrait -- this is what
            # identifies a profile block sitting BESIDE the portrait, not
            # merely above/below it.
            overlap = max(0.0, min(it, tt) - max(ib, tb))
            overlap_ratio = overlap / min(i_height, t_height)

            # Column adjacency: horizontal overlap between the image's and
            # text block's x-ranges (same column), or a horizontal gap no
            # wider than 1.5x the portrait's own width (adjacent column).
            h_overlap = max(0.0, min(ir, tr) - max(il, tl))
            same_column = h_overlap > 0 or gap_x <= (i_width * 1.5)

            distance = (gap_x ** 2 + gap_y ** 2) ** 0.5
            # A same-column block is exempt from the distance cap on the
            # extended pass only -- a directory-style profile column can
            # place the matching name/designation well below the nearest
            # unrelated line, and column membership (not raw distance) is
            # the real evidence of belonging to the same portrait.
            if distance > distance_cap and not (extended and same_column):
                continue

            # Composite score (lower = better): raw distance, discounted for
            # strong vertical overlap and same-column layout. Reading order
            # is kept only as a final tiebreaker. This score is used only to
            # order candidates for grouping/display -- it is NEVER, by
            # itself, treated as proof of identity association.
            score = distance - (overlap_ratio * 80.0) - (25.0 if same_column else 0.0)

            candidates.append({
                "text": t_str,
                "type": el_type,
                "bbox": {"l": tl, "r": tr, "t": tt, "b": tb},
                "gap_x": round(gap_x, 2),
                "gap_y": round(gap_y, 2),
                "vertical_overlap_ratio": round(overlap_ratio, 3),
                "same_column": same_column,
                "distance": round(distance, 2),
                "score": round(score, 2),
                "reading_order_index": order_idx,
            })

        candidates.sort(key=lambda c: (c["score"], c["reading_order_index"]))
        return candidates

    @staticmethod
    def _group_into_regions(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Groups candidate blocks into logical profile/content regions using
        reading order + layout adjacency (a name line immediately followed
        by a designation line and a biography paragraph, stacked in the
        same column with small gaps, is one region -- not three unrelated
        text hits). A block far from its reading-order neighbor, or in a
        different column, starts a new region.
        """
        if not candidates:
            return []

        ordered = sorted(candidates, key=lambda c: c["reading_order_index"])
        regions: List[List[Dict[str, Any]]] = [[ordered[0]]]

        for prev, cur in zip(ordered, ordered[1:]):
            same_region = False
            if cur["reading_order_index"] - prev["reading_order_index"] <= 2:
                p_box, c_box = prev["bbox"], cur["bbox"]
                vertical_gap = max(0.0, p_box["b"] - c_box["t"], c_box["b"] - p_box["t"])
                h_overlap = max(0.0, min(p_box["r"], c_box["r"]) - max(p_box["l"], c_box["l"]))
                same_col = h_overlap > 0 or abs(p_box["l"] - c_box["l"]) < 30.0
                if vertical_gap <= SpatialDocumentContextGrounder.MAX_REGION_GAP and same_col:
                    same_region = True
            if same_region:
                regions[-1].append(cur)
            else:
                regions.append([cur])

        region_summaries = []
        for members in regions:
            members_sorted = sorted(members, key=lambda m: m["reading_order_index"])
            text = "\n".join(m["text"] for m in members_sorted)
            ls = [m["bbox"]["l"] for m in members_sorted]
            rs = [m["bbox"]["r"] for m in members_sorted]
            ts = [m["bbox"]["t"] for m in members_sorted]
            bs = [m["bbox"]["b"] for m in members_sorted]
            region_summaries.append({
                "text": text,
                "bbox": {"l": min(ls), "r": max(rs), "t": max(ts), "b": min(bs)},
                "member_count": len(members_sorted),
                "min_distance": min(m["distance"] for m in members_sorted),
                "max_vertical_overlap_ratio": max(m["vertical_overlap_ratio"] for m in members_sorted),
                "any_same_column": any(m["same_column"] for m in members_sorted),
                "reading_order_index": members_sorted[0]["reading_order_index"],
            })
        return region_summaries

    @staticmethod
    def _evaluate_region(region: Dict[str, Any]) -> Dict[str, Any]:
        """
        Scores a region on real identity evidence only. A heading, section
        title, or generic/unrelated narrative paragraph carries no name and
        no designation, so it scores zero name/designation evidence and is
        rejected regardless of how spatially close it is.
        """
        text = region["text"]
        identity = extract_generic_person_identity(text) or extract_untitled_name_near_designation(text)
        name_evidence = identity[0] if identity else None
        designation_from_name = identity[1] if identity else None
        desig_match = _DESIGNATION_PATTERN.search(text)
        designation_evidence = designation_from_name or (desig_match.group(1) if desig_match else None)
        biography_evidence = _looks_like_biography_text(text)

        distance_ratio = max(
            0.0,
            (SpatialDocumentContextGrounder.EXTENDED_ASSOCIATION_DISTANCE - region["min_distance"])
            / SpatialDocumentContextGrounder.EXTENDED_ASSOCIATION_DISTANCE,
        )
        adjacency_score = (
            distance_ratio * 15.0
            + min(region["max_vertical_overlap_ratio"], 1.0) * 10.0
            + (5.0 if region["any_same_column"] else 0.0)
        )

        score = 0.0
        if name_evidence:
            score += 50.0
        if designation_evidence:
            score += 25.0
        if biography_evidence:
            score += 10.0
        score += adjacency_score

        return {
            **region,
            "name_evidence": name_evidence,
            "designation_evidence": designation_evidence,
            "biography_evidence": biography_evidence,
            "adjacency_score": round(adjacency_score, 2),
            "evidence_score": round(score, 2),
        }

    @staticmethod
    def ground(
        image_id: str,
        bbox: Any,
        doc_elements_on_page: List[Dict[str, Any]],
        page_number: int = 0,
    ) -> Dict[str, Any]:
        """
        Returns, on success: {entity_name, designation, nearby_text,
        confidence, selected_region, debug}.
        On failure: {entity_name: None, reason: "<exact reason>", debug}.
        Every call logs: portrait bbox -> candidate regions -> name evidence
        -> designation evidence -> biography evidence -> selected region ->
        confidence, OR the exact rejection reason -- never a silent guess.
        """
        il, ir, it, ib = _get_bbox_coords(bbox) if bbox else (0.0, 0.0, 0.0, 0.0)
        if il == 0 and ir == 0 and it == 0 and ib == 0:
            logger.debug(f"[spatial_document_context] {image_id}: no usable portrait bbox -- skipping.")
            return {"entity_name": None, "reason": "missing_portrait_bbox", "debug": {}}

        coords = (il, ir, it, ib)

        def _resolve(extended: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
            candidates = SpatialDocumentContextGrounder._candidate_blocks(coords, doc_elements_on_page, extended=extended)
            regions = SpatialDocumentContextGrounder._group_into_regions(candidates)
            evaluated = [SpatialDocumentContextGrounder._evaluate_region(r) for r in regions]
            evaluated.sort(key=lambda r: r["evidence_score"], reverse=True)
            qualifying = [r for r in evaluated if r["name_evidence"]]
            best = qualifying[0] if qualifying else None
            return best, evaluated

        best_region, evaluated_regions = _resolve(extended=False)
        search_mode = "normal"
        if best_region is None:
            logger.info(
                f"[spatial_document_context] image={image_id}: no region with name evidence in normal "
                f"search radius ({SpatialDocumentContextGrounder.MAX_ASSOCIATION_DISTANCE:.0f}pt) -- "
                f"widening search (extended distance + full same-column span)."
            )
            best_region, evaluated_regions = _resolve(extended=True)
            search_mode = "extended"

        debug_regions = [
            {
                "text_preview": r["text"][:100],
                "bbox": r["bbox"],
                "name_evidence": r["name_evidence"],
                "designation_evidence": r["designation_evidence"],
                "biography_evidence": r["biography_evidence"],
                "min_distance": r["min_distance"],
                "evidence_score": r["evidence_score"],
            }
            for r in evaluated_regions[:8]
        ]
        logger.debug(
            f"[spatial_document_context] image={image_id} portrait_bbox=(l={il:.1f}, r={ir:.1f}, "
            f"t={it:.1f}, b={ib:.1f}) search_mode={search_mode} candidate_regions={debug_regions}"
        )

        if not evaluated_regions:
            logger.info(
                f"[spatial_document_context] image={image_id}: association FAILED -- no text block "
                f"found near the portrait bbox on page {page_number}, even after widening the search."
            )
            return {"entity_name": None, "reason": "no_candidate_regions_found", "debug": {"regions": debug_regions}}

        if best_region is None:
            top = evaluated_regions[0]
            logger.info(
                f"[spatial_document_context] image={image_id}: association FAILED (rejected) -- "
                f"{len(evaluated_regions)} candidate region(s) found (search_mode={search_mode}), but none "
                f"contain a recognizable person name (closest/highest-scoring region: "
                f"'{top['text'][:80]}', designation_evidence={top['designation_evidence']}, "
                f"biography_evidence={top['biography_evidence']}). Rejected as heading/section-title/"
                f"unrelated narrative -- distance alone is not proof of association."
            )
            return {
                "entity_name": None,
                "reason": "no_person_name_evidence_in_any_region",
                "debug": {"regions": debug_regions},
            }

        name, designation = best_region["name_evidence"], best_region["designation_evidence"]
        # Confidence is earned strictly from the evidence actually found in
        # the selected region -- never a flat constant regardless of
        # content. A name alone (no designation, no biography language, weak
        # adjacency) sits at the low end; name + designation + biography
        # narrative + strong adjacency sits at the high end.
        confidence = 0.55
        if designation:
            confidence += 0.15
        if best_region["biography_evidence"]:
            confidence += 0.10
        confidence += min(best_region["adjacency_score"] / 30.0, 1.0) * 0.10
        if search_mode == "extended":
            # Slightly more conservative when the match required widening
            # the search radius beyond the immediate vicinity.
            confidence -= 0.05
        confidence = round(max(0.50, min(0.90, confidence)), 2)

        logger.info(
            f"[spatial_document_context] image={image_id} search_mode={search_mode} -> selected profile "
            f"region text='{best_region['text'][:80]}' bbox={best_region['bbox']} "
            f"name_evidence='{name}' designation_evidence='{designation}' "
            f"biography_evidence={best_region['biography_evidence']} confidence={confidence}"
        )
        return {
            "entity_name": name,
            "designation": designation,
            "nearby_text": best_region["text"],
            "confidence": confidence,
            "selected_region": best_region,
            "debug": {"regions": debug_regions},
        }


class HierarchicalLayoutGrounder:
    """
    Implements a hierarchical caption and layout-grounding strategy for extracted document images.
    
    Association Priority Hierarchy:
    1. explicit_caption: If a document caption is present, store it exactly as the highest-confidence association (0.95 - 1.0).
    2. same_card_layout: For portraits, cards, grids, tables, or repeated layouts, associate the image with text inside
       its own spatial region/card using bounding boxes, row/column alignment, and layout containment (0.85 - 0.95).
    3. section_spatial_context: For uncaptioned large/full-width visuals (occupying significant portion of page),
       store section heading, page title, and surrounding spatial context. Do NOT invent an explicit caption (0.75 - 0.85).
    4. surrounding_text: Extract text_before and text_after on the same page/section (0.60 - 0.75).
    5. vlm_semantic_description: VLM semantic description (0.40 - 0.60).
    6. none: Never assign person/entity if confidence is insufficient.
    
    Importance Scoring:
    - HIGH: Verified portraits, charts/graphs/diagrams, major logos, full-page/large visuals (>=20% page area)
    - MEDIUM: Section photos, facility/equipment pictures, contextual figures
    - LOW: Decorative line separators, tiny icons (<100x100), background borders, repeated ornamental graphics
    
    Retrieval Gating:
    - retrievable = True for HIGH and MEDIUM
    - retrievable = False for LOW / decorative elements (excluded from visual query retrieval)
    """

    @staticmethod
    def ground_image(
        image_id: str,
        page_number: int,
        bbox: Any,
        doc_elements_on_page: List[Dict[str, Any]],
        doc_title: Optional[str] = None,
        active_section: Optional[str] = None,
        explicit_caption: Optional[str] = None,
        ocr_text: Optional[str] = None,
        raw_image_type: Optional[str] = None,
        vlm_description: Optional[str] = None,
        page_width: float = 595.0,
        page_height: float = 842.0
    ) -> Dict[str, Any]:
        """
        Applies hierarchical caption and layout grounding to assign grounded JSON metadata,
        importance scoring, and retrieval gating to an extracted image.
        
        Priority:
        1. Explicit caption: If a document caption exists, store exactly as title and association_method="explicit_caption".
        2. Same-card/layout text: Analyze spatially associated text above/below/beside/inside container. Most relevant text as title, secondary as subtitle.
        3. Section context: Use section heading plus nearby text before/after to generate short grounded title and optional subtitle.
        4. Surrounding text: Use immediate nearby text context.
        5. VLM fallback: Semantic title/description from visual when layout context is insufficient.
        """
        # 1. Geometry & Dimensions
        w, h = 0.0, 0.0
        il, ir, it, ib = 0.0, 0.0, 0.0, 0.0
        bbox_data = {}
        if bbox:
            if isinstance(bbox, dict):
                il, ir = float(bbox.get("l", 0) or 0), float(bbox.get("r", 0) or 0)
                it, ib = float(bbox.get("t", 0) or 0), float(bbox.get("b", 0) or 0)
                bbox_data = bbox
            else:
                il, ir = float(getattr(bbox, "l", 0) or 0), float(getattr(bbox, "r", 0) or 0)
                it, ib = float(getattr(bbox, "t", 0) or 0), float(getattr(bbox, "b", 0) or 0)
                bbox_data = bbox.model_dump() if hasattr(bbox, "model_dump") else (bbox.dict() if hasattr(bbox, "dict") else {"l": il, "r": ir, "t": it, "b": ib})
            w = abs(ir - il)
            h = abs(it - ib)

        page_area = max(page_width * page_height, 1.0)
        image_area = w * h
        area_ratio = image_area / page_area
        aspect_ratio = (w / h) if h > 0 else 1.0

        # 2. Surrounding Text Extraction (text_before and text_after)
        text_before = None
        text_after = None
        
        # Sort text elements by vertical reading position (Docling bottom-left coords: higher t = higher up)
        text_blocks = []
        for el in doc_elements_on_page:
            t_str = (el.get("text") or "").strip()
            if not t_str or el.get("type") in ("image", "PictureItem", "ImageItem"):
                continue
            t_box = el.get("metadata", {}).get("bbox") or el.get("bbox") or {}
            if isinstance(t_box, dict):
                ty = float(t_box.get("t", 0) or 0)
            else:
                ty = float(getattr(t_box, "t", 0) or 0)
            text_blocks.append((ty, t_str))

        text_blocks.sort(key=lambda x: x[0], reverse=True)
        
        for ty, t_str in text_blocks:
            if ty > it and not text_before:
                text_before = t_str
            elif ty < ib and not text_after:
                text_after = t_str

        # 3. Association Priority Execution
        title = None
        subtitle = None
        entity_name = None
        designation = None
        spatial_nearby_text = None
        final_caption = None
        final_explicit_caption = None
        layout_context = "unanchored_visual"
        association_method = "none"
        association_confidence = 0.50
        image_type = raw_image_type or "Photo"

        # Check Priority 1: Explicit Caption (ignore generic/synthetic strings)
        synthetic_prefixes = ("figure on page", "portrait of", "visual graphic", "image on page", "picture on page")
        if explicit_caption and explicit_caption.strip() and not explicit_caption.strip().lower().startswith(synthetic_prefixes):
            final_explicit_caption = explicit_caption.strip()
            title = final_explicit_caption
            subtitle = active_section.strip() if (active_section and active_section != final_explicit_caption) else None
            final_caption = final_explicit_caption
            association_method = "explicit_caption"
            association_confidence = 0.98
            layout_context = "explicit_captioned_figure"

            # A captioned figure whose caption names a real person (any
            # person, not just a fixed roster) is grounded as a portrait
            # directly from that document text.
            identity = extract_generic_person_identity(final_explicit_caption)
            if identity:
                entity_name, designation = identity
                title = entity_name
                subtitle = designation or subtitle
                image_type = "Portrait Photo"
                final_caption = f"Portrait of {entity_name} ({designation})" if designation else f"Portrait of {entity_name}"

        # Check Priority 2: Structured Same-Card / Layout Text (Portraits & Card Containers)
        if not final_explicit_caption:
            spatial_card_match = PortraitSpatialValidator.match_person_to_portrait_spatial(bbox, doc_elements_on_page)
            if spatial_card_match:
                entity_name = spatial_card_match["person_name"]
                designation = spatial_card_match["designation"]
                # The person's actual biography/qualifications paragraph on
                # THIS card, if one was found directly beneath the matched
                # name/designation line -- never the generic single-nearest
                # text_before/text_after block, which can just as easily be
                # an unrelated heading fragment or (in a multi-person
                # directory grid) the very next person's own name.
                spatial_nearby_text = spatial_card_match.get("biography_text")
                title = entity_name
                subtitle = designation
                image_type = "Portrait Photo"
                layout_context = f"portrait_card_{spatial_card_match.get('layout_alignment', 'horizontal')}"
                association_method = "same_card_layout"
                association_confidence = 0.92
                final_caption = f"Portrait of {entity_name} ({designation})" if designation else f"Portrait of {entity_name}"

        # Check Priority 2b: Signature Association -- generic detection via a
        # fixed set of ordinary English signature-block phrases (never any
        # person/organization name), then reuses the same real-text-only name
        # extraction as portraits so the signature is attributed to whoever
        # is actually named beside/under it in the document, not a guess.
        # Runs BEFORE the general OCR-grounded portrait check below, since a
        # signature block's OCR text also contains a titled name and would
        # otherwise always be misread as a portrait.
        _SIGNATURE_INDICATORS = (
            "signature", "signed by", "authorised signatory", "authorized signatory",
            "for and on behalf of", "sd/-", "digitally signed"
        )
        is_signature_block = False
        if not final_explicit_caption and not entity_name:
            signature_context = " ".join(
                filter(None, [ocr_text, explicit_caption, text_before, text_after])
            ).lower()
            if any(ind in signature_context for ind in _SIGNATURE_INDICATORS):
                is_signature_block = True
                sig_identity = None
                for candidate_text in (ocr_text, text_before, text_after):
                    sig_identity = (
                        extract_generic_person_identity(candidate_text)
                        or extract_untitled_name_near_designation(candidate_text)
                    )
                    if sig_identity:
                        break
                image_type = "Signature"
                layout_context = "signature_block"
                if sig_identity:
                    entity_name, designation = sig_identity
                    title = entity_name
                    subtitle = designation or "Signature"
                    association_method = "signature_text_grounded"
                    association_confidence = 0.85
                    final_caption = (
                        f"Signature of {entity_name} ({designation})" if designation
                        else f"Signature of {entity_name}"
                    )

        # Check Priority 2c: Generic OCR-Grounded Identity (ANY person, not a
        # fixed roster) -- fires only when no explicit caption, spatially
        # matched card, or signature-block indicator identified a person,
        # and only on a titled name (Mr./Ms./Dr./Shri/Smt./Er.) actually
        # present in the image's own OCR text, so it never invents a name.
        if not final_explicit_caption and not entity_name and not is_signature_block and ocr_text:
            ocr_identity = extract_generic_person_identity(ocr_text)
            if ocr_identity:
                entity_name, designation = ocr_identity
                title = entity_name
                subtitle = designation
                image_type = "Portrait Photo"
                layout_context = "ocr_grounded_portrait"
                association_method = "ocr_grounded_identity"
                association_confidence = 0.80
                final_caption = f"Portrait of {entity_name} ({designation})" if designation else f"Portrait of {entity_name}"

        # Geometry check (computed once, reused below): does this bbox fit a
        # single individual portrait photograph? Portrait-shaped images take
        # a dedicated identity-evidence-gated path (2d) and must NEVER fall
        # through to the generic distance-only section/nearest-text tiers
        # (3 & 4) below -- that is what previously let an unrelated heading
        # or narrative paragraph become a portrait's "identity" just because
        # it was spatially closest.
        is_portrait_shape, _geom_reason = PortraitSpatialValidator.validate_portrait_geometry(bbox)

        # Check Priority 2d: Portrait-Specific Profile Region Association.
        # Detects every text block around the portrait, groups them into
        # logical profile regions (layout + reading order + column
        # adjacency), and only accepts a region that contains real person-
        # name evidence (designation/biography language and adjacency only
        # raise confidence, never substitute for a name). This is what
        # catches a genuine profile block beside a portrait that priorities
        # 1/2/2b/2c did not already resolve -- without ever accepting a
        # heading or unrelated narrative just because it was nearby.
        if not final_explicit_caption and not entity_name and not is_signature_block:
            if is_portrait_shape:
                spatial_ctx = SpatialDocumentContextGrounder.ground(
                    image_id=image_id,
                    bbox=bbox_data,
                    doc_elements_on_page=doc_elements_on_page,
                    page_number=page_number,
                )
                if spatial_ctx.get("entity_name"):
                    entity_name = spatial_ctx["entity_name"]
                    designation = spatial_ctx.get("designation")
                    spatial_nearby_text = spatial_ctx.get("nearby_text")
                    title = entity_name
                    subtitle = designation
                    image_type = "Portrait Photo"
                    layout_context = "spatial_document_context"
                    association_method = "spatial_document_context"
                    association_confidence = spatial_ctx.get("confidence", 0.70)
                    final_caption = f"Portrait of {entity_name} ({designation})" if designation else f"Portrait of {entity_name}"
            else:
                logger.debug(
                    f"[spatial_document_context] {image_id}: skipped -- bbox does not match portrait "
                    f"geometry ({_geom_reason})."
                )

        # Check Priority 3 & 4: Section Context and Spatially Nearest Text
        # for Uncaptioned Visuals -- NEVER for a portrait-shaped image. A
        # portrait with no verified identity must stay unresolved rather
        # than adopt a nearby heading/section title/unrelated paragraph as
        # if it were the person's identity (handled explicitly below).
        if not final_explicit_caption and not entity_name and not is_portrait_shape:
            sec_candidate = (active_section or "").strip()
            # If large/full-width visual or active section is prominent
            if sec_candidate and (area_ratio >= 0.25 or w >= 400 or not doc_elements_on_page):
                title = sec_candidate
                subtitle = text_before[:120].strip() if text_before else (text_after[:120].strip() if text_after else None)
                association_method = "section_spatial_context"
                association_confidence = 0.82
                layout_context = "full_page_visual" if area_ratio >= 0.35 else "section_figure"
                final_caption = f"Visual graphic on Page {page_number} ({title})"
            elif doc_elements_on_page:
                # Find spatially nearest text element on the same page
                nearest_text_block = None
                min_spatial_dist = 999999.0
                for el in doc_elements_on_page:
                    t_str = (el.get("text") or "").strip()
                    if not t_str or len(t_str) < 5 or el.get("type") in ("image", "PictureItem", "ImageItem", "heading"):
                        continue
                    t_box = el.get("metadata", {}).get("bbox") or el.get("bbox") or {}
                    if isinstance(t_box, dict):
                        tl, tr, tt, tb = float(t_box.get("l", 0) or 0), float(t_box.get("r", 0) or 0), float(t_box.get("t", 0) or 0), float(t_box.get("b", 0) or 0)
                    else:
                        tl = float(getattr(t_box, "l", 0) or 0)
                        tr = float(getattr(t_box, "r", 0) or 0)
                        tt = float(getattr(t_box, "t", 0) or 0)
                        tb = float(getattr(t_box, "b", 0) or 0)

                    gap_x = max(0.0, tl - ir, il - tr)
                    gap_y = max(0.0, tb - it, ib - tt)
                    spatial_dist = (gap_x ** 2 + gap_y ** 2) ** 0.5

                    if spatial_dist < min_spatial_dist:
                        min_spatial_dist = spatial_dist
                        nearest_text_block = t_str

                if nearest_text_block and min_spatial_dist <= 130.0:
                    first_sent = nearest_text_block.split(".")[0].strip()
                    title = first_sent[:85] if first_sent else nearest_text_block[:85]
                    subtitle = sec_candidate if sec_candidate else (text_after[:120].strip() if text_after else None)
                    association_method = "spatially_nearest_text"
                    association_confidence = 0.85
                    layout_context = "spatially_anchored_figure"
                    final_caption = f"Figure on Page {page_number} ({title})"
                elif sec_candidate:
                    title = sec_candidate
                    subtitle = text_before[:120].strip() if text_before else (text_after[:120].strip() if text_after else None)
                    association_method = "section_spatial_context"
                    association_confidence = 0.82
                    layout_context = "section_figure"
                    final_caption = f"Visual graphic on Page {page_number} ({title})"
                elif doc_title:
                    title = doc_title.strip()
                    subtitle = text_before[:120].strip() if text_before else (text_after[:120].strip() if text_after else None)
                    association_method = "section_spatial_context"
                    association_confidence = 0.75
                    layout_context = "section_figure"
                    final_caption = f"Figure on Page {page_number} ({title})"

        # Check Priority 4b: Surrounding Text -- NEVER for a portrait-shaped
        # image, for the same reason as Priority 3 & 4: unverified nearby
        # prose (whatever precedes/follows on the page) is not evidence of
        # who is in the photo.
        if association_method == "none" and not is_portrait_shape and (text_before or text_after):
            title = text_before[:80].strip() if text_before else text_after[:80].strip()
            subtitle = text_after[:120].strip() if (text_before and text_after) else None
            layout_context = "embedded_visual"
            association_method = "surrounding_text"
            association_confidence = 0.68
            final_caption = f"Figure on Page {page_number}"

        # Check Priority 4c: Unresolved Portrait. A portrait-shaped image
        # that reaches this point has explicitly failed every identity-
        # evidence check (explicit caption, same-card layout, signature,
        # OCR-grounded identity, and the profile-region search above,
        # including its widened/extended pass). It is left honestly
        # unresolved -- no entity_name/designation/nearby_text, no borrowed
        # heading or unrelated narrative as a fake title, and a confidence
        # that reflects genuine uncertainty -- rather than silently
        # contaminating retrieval with unrelated text content.
        if association_method == "none" and is_portrait_shape:
            title = f"Unidentified Portrait on Page {page_number}"
            subtitle = None
            layout_context = "unresolved_portrait"
            association_method = "unresolved_portrait"
            association_confidence = 0.30
            final_caption = f"Unidentified portrait on Page {page_number}"
            logger.info(
                f"[spatial_document_context] image={image_id}: portrait left UNRESOLVED -- "
                f"no verified person-profile evidence found; not attaching any nearby heading, "
                f"section title, or unrelated narrative as identity context."
            )

        # Check Priority 5: VLM Fallback
        if association_method == "none":
            vlm_text = vlm_description.strip() if vlm_description else ""
            if vlm_text:
                first_sentence = vlm_text.split(".")[0].strip()
                title = first_sentence[:80] if first_sentence else f"Visual on Page {page_number}"
            else:
                title = f"Document visual graphic on Page {page_number}"
            subtitle = None
            layout_context = "vlm_contextual_visual"
            association_method = "vlm_semantic_description"
            association_confidence = 0.55
            final_caption = f"Visual on Page {page_number}"

        # Guard: Negative guard against unassociated entity assignment.
        # ocr_grounded_identity and signature_text_grounded are included
        # because they -- like same_card_layout and explicit_caption -- only
        # ever get set from a titled name found directly in real document
        # text (never a model-inferred guess).
        if association_method not in (
            "same_card_layout", "explicit_caption", "ocr_grounded_identity",
            "signature_text_grounded", "spatial_document_context",
        ):
            entity_name = None
            designation = None

        # Check Logo Specialization
        is_logo = (
            "logo" in (image_type or "").lower() or
            "logo" in (vlm_description or "").lower() or
            "logo" in (explicit_caption or "").lower() or
            (page_number in (1, 2, 3, 4, 5) and (
                any("logo" in str(el.get("text", "")).lower() for el in doc_elements_on_page) or
                "logo" in (vlm_description or "").lower()
            ))
        )
        if is_logo:
            # Organization name is derived generically: a real legal-entity
            # name found in nearby text/caption/description, else the
            # document's own title -- never a hardcoded company name.
            org_name = (
                extract_generic_organization_name([explicit_caption, final_caption, vlm_description, active_section])
                or (doc_title.strip() if doc_title else None)
                or "the associated organization"
            )
            image_type = "Logo"
            title = f"Company Logo - {org_name}"
            subtitle = "Official Brand Identity"
            final_caption = f"Company Logo of {org_name}"
            final_explicit_caption = final_caption if not final_explicit_caption else final_explicit_caption
            association_method = "explicit_caption" if final_explicit_caption else "layout_brand_identity"
            association_confidence = 0.96
            layout_context = "brand_identity_asset"
            entity_name = None
            designation = None

        # 4. Importance Scoring and Retrieval Gating (Separate Decisions)
        # Low value check: only tiny icons / empty separator lines are non-retrievable
        is_tiny_icon = (w > 0 and h > 0 and w < 35 and h < 35)
        is_extreme_divider = (w > 0 and h > 0 and (aspect_ratio > 8.0 or aspect_ratio < 0.10) and area_ratio < 0.005)
        is_genuinely_low_value = (is_tiny_icon or is_extreme_divider) and not is_logo and not explicit_caption

        # Determine Image Type if still generic
        if image_type in ("Photo", "Image", "Diagram", "PictureItem", "Figure"):
            combined_desc = f"{final_caption or ''} {title or ''} {subtitle or ''} {active_section or ''} {vlm_description or ''}".lower()
            if entity_name or association_method == "same_card_layout" or "portrait" in combined_desc or "director" in combined_desc:
                image_type = "Portrait Photo"
            elif is_logo or "logo" in combined_desc:
                image_type = "Logo"
            elif "signature" in combined_desc or "signatory" in combined_desc:
                image_type = "Signature"
            elif is_genuinely_low_value:
                image_type = "Decorative"
            elif any(k in combined_desc for k in ("chart", "graph", "growth", "performance", "bar graph", "pie chart", "trend")):
                image_type = "Chart/Graph"
            elif any(k in combined_desc for k in ("diagram", "flowchart", "flow chart", "system", "architecture", "process flow", "schematic")):
                image_type = "Diagram"
            elif any(k in combined_desc for k in ("map", "geographical", "locations", "presence")):
                image_type = "Map"
            else:
                image_type = "Photo"

        # Determine Importance Score & Retrievability (Strict Retrievability Rules)
        # A verified Logo, Portrait, Chart, Diagram, Graph, Map, or Captioned Figure must remain retrievable=True
        if image_type == "Portrait Photo" or "portrait" in image_type.lower() or entity_name:
            importance_score = "HIGH"
            retrievable = True
        elif image_type == "Logo" or is_logo:
            importance_score = "HIGH"
            retrievable = True
        elif association_method == "explicit_caption":
            importance_score = "HIGH"
            retrievable = True
        elif image_type in ("Chart", "Graph", "Chart/Graph", "Diagram", "Table", "Map", "Flowchart", "Architecture", "Signature"):
            importance_score = "HIGH"
            retrievable = True
        elif is_genuinely_low_value or image_type == "Decorative":
            # The ONLY case that suppresses retrieval: a tiny icon or an
            # extreme-aspect-ratio divider line with no logo/caption signal
            # at all -- i.e. genuinely not a meaningful visual asset. Every
            # other image (regardless of size, aspect ratio, or whether it
            # has a caption) stays retrievable=True; missing captions or
            # modest dimensions are never, by themselves, grounds to drop a
            # meaningful image from search.
            importance_score = "LOW"
            retrievable = False
        elif area_ratio >= 0.05 or (w >= 80 and h >= 60):
            importance_score = "MEDIUM"
            retrievable = True
        else:
            # Smaller/uncaptioned photos (project/site photos, inline
            # figures, small diagrams) are still meaningful visual content
            # -- they are ranked lower for relevance, not excluded from
            # retrieval.
            importance_score = "MEDIUM"
            retrievable = True

        # If decorative/low-value separator, ensure entity is clean
        if is_genuinely_low_value or image_type == "Decorative":
            entity_name = None
            designation = None

        # Build Objects, Keywords, and Detected Entities
        objects = []
        keywords = []
        detected_entities = []

        if entity_name:
            role_part = f" ({designation})" if designation else ""
            detected_entities = [f"{entity_name}{role_part}", entity_name]
            keywords = ["portrait", "photo", "leadership", "director", "board of directors", entity_name]
            if designation:
                keywords.append(designation)
            objects = ["portrait", "person", "headshot", "photograph"]
        elif image_type == "Logo" or is_logo:
            logo_org = org_name if is_logo else (
                extract_generic_organization_name([explicit_caption, final_caption, vlm_description, active_section])
                or (doc_title.strip() if doc_title else None)
                or "the associated organization"
            )
            detected_entities = [logo_org]
            keywords = ["logo", "company logo", "brand", "emblem", "insignia", logo_org]
            objects = ["logo", "emblem", "brand mark"]
        elif image_type in ("Chart", "Graph", "Chart/Graph", "Diagram", "Table"):
            keywords = [image_type.lower(), "metrics", "financial", "data", active_section or "report"]
            objects = [image_type.lower(), "chart", "graphic"]
        else:
            if image_type:
                keywords.append(image_type.lower())
            if active_section:
                keywords.append(active_section)
            if title and title != active_section:
                keywords.append(title)
            objects = ["image", "figure", "visual graphic"]

        # nearby_text carries identity-bearing profile text only, and only
        # when it was actually found as evidence for THIS person (the
        # region-grouped match from spatial_document_context, or the
        # biography paragraph found directly beneath the matched card line
        # for same_card_layout). It must NEVER fall back to the generic
        # single-nearest text_before/text_after for an identity-resolved or
        # unresolved portrait -- that single-nearest block can just as
        # easily be an unrelated heading fragment or (in a multi-person
        # directory grid) literally the next person's own name, which is
        # exactly the "unrelated heading/narrative treated as identity
        # context" contamination this pipeline must avoid. Non-portrait
        # visuals (charts, diagrams, generic figures) still use
        # text_before/text_after here as ordinary surrounding context, which
        # was always their intended, non-identity meaning.
        _IDENTITY_ASSOCIATION_METHODS = (
            "same_card_layout", "explicit_caption", "ocr_grounded_identity",
            "signature_text_grounded", "spatial_document_context", "unresolved_portrait",
        )
        if association_method in _IDENTITY_ASSOCIATION_METHODS:
            nearby_text = spatial_nearby_text
        else:
            nearby_text = spatial_nearby_text or text_before or text_after

        if entity_name and not vlm_description:
            bio_snippet = (nearby_text or "")[:200]
            semantic_description = (
                f"Portrait of {entity_name}"
                + (f", {designation}" if designation else "")
                + (f". {bio_snippet}" if bio_snippet else f" on Page {page_number}.")
            )
        else:
            semantic_description = vlm_description or f"{image_type} on Page {page_number} under section '{active_section or 'Document Content'}'."

        return {
            "image_id": image_id,
            "image_path": None,
            "page": page_number,
            "bounding_box": bbox_data,
            "image_type": image_type,
            "title": title or f"Visual on Page {page_number}",
            "subtitle": subtitle,
            "explicit_caption": final_explicit_caption,
            "caption_text": final_caption,
            "entity_name": entity_name,
            "designation": designation,
            "section_heading": active_section,
            "text_before": text_before,
            "text_after": text_after,
            "nearby_text": nearby_text,
            "semantic_description": semantic_description,
            "keywords": keywords,
            "importance_score": importance_score,
            "retrievable": retrievable,
            "association_method": association_method,
            "association_confidence": association_confidence,
            # Backward-compatible fields
            "caption": final_caption or title or f"Visual on Page {page_number}",
            "confidence": association_confidence,
            "layout_context": layout_context,
            "ocr_text": ocr_text,
            "objects": objects,
            "detected_entities": detected_entities
        }


class ImageRetrievalValidator:
    """
    Final retrieval validation layer enforcing 5 strict checks:
    1. Query target identification (Portrait, Multi-Portrait, Board Collection, Logo, Captioned Figure/Table, Chart/Diagram, Pure Text)
    2. Metadata match (Strict entity/name match, rejecting surname-only/generic keyword collisions, 1-to-1 matching)
    3. Page/layout consistency (Correct page and layout alignment for the queried asset)
    4. Physical file existence (Verifying file is present on disk and non-empty)
    5. Correct image type (Ensuring image_type matches query intent and is retrievable, never Decorative)

    If ANY validation check fails, returns False (discards image) to guarantee zero incorrect image associations.
    """

    VISUAL_TRIGGERS = [
        "image", "images", "figure", "figures", "diagram", "diagrams", "chart", "charts",
        "photo", "photos", "photograph", "photographs", "picture", "pictures", "portrait",
        "portraits", "visual", "visuals", "graph", "graphs", "plot", "plots", "illustration",
        "illustrations", "headshot", "headshots", "look like", "show me", "along with photos",
        "along with their photos", "with photos", "with photo", "logo", "company logo", "brand logo",
        "show logo", "show the logo", "give the logo", "give logo", "can you show", "can you give",
        "director's photo", "directors photo", "show the image", "show image", "photo of", "image of",
        "picture of", "portrait of", "photos of", "images of", "pictures of", "portraits of"
    ]

    @classmethod
    def _ambiguous_token_owner_count(cls, token: str, known_entities: List[str]) -> int:
        """
        Counts how many DISTINCT entities in the document's own known-entity
        registry share `token` as one of their name parts. Purely derived
        from the document's own grounded entities -- no fixed surname list --
        so "photo of Todi" is correctly flagged ambiguous only when the
        document itself actually contains 2+ people whose name includes
        "todi", and is a normal (non-ambiguous) single-person lookup for any
        other document.
        """
        owners = set()
        for ent in known_entities or []:
            ent_norm = cls.normalize_name(ent)
            if token in ent_norm.split():
                owners.add(ent_norm)
        return len(owners)

    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Normalizes names by stripping honorifics, punctuation, and collapsing whitespace.
        """
        import re
        if not name:
            return ""
        n = str(name).lower()
        for prefix in ["mr.", "mr ", "mrs.", "mrs ", "ms.", "ms ", "dr.", "dr ", "shri ", "smt "]:
            if n.startswith(prefix):
                n = n[len(prefix):]
        n = re.sub(r"[^\w\s]", " ", n)
        return re.sub(r"\s+", " ", n).strip()

    @classmethod
    def is_visual_query(cls, query: str, intent: Optional[str] = None) -> bool:
        """
        Determines whether a user query has explicit visual intent.
        Pure text queries return False.
        """
        import re
        if intent in ("visual", "person_portrait_visual"):
            return True
        q_lower = query.lower()
        return any(re.search(rf"\b{re.escape(vt)}\b", q_lower) for vt in cls.VISUAL_TRIGGERS)

    @classmethod
    def extract_person_names_from_query(cls, query: str, known_entities: Optional[List[str]] = None) -> List[str]:
        """
        Dynamically and generically extracts individual person names from a query.
        Handles single names, multi-person queries with 'and' / '&' / commas, and known entities.
        """
        import re
        q_lower = query.lower().strip()

        # Check known entities from the document's own grounded entity
        # registry (passed in by the caller, e.g. every image chunk's
        # entity_name) -- never a fixed roster.
        matched_from_entities = []
        all_known = list(known_entities or [])

        for ent in all_known:
            ent_norm = cls.normalize_name(ent)
            if len(ent_norm) > 2 and re.search(rf"\b{re.escape(ent_norm)}\b", q_lower):
                if ent_norm not in matched_from_entities:
                    matched_from_entities.append(ent_norm)

        # Remove common query prefixes and phrasing
        clean_q = q_lower
        strip_phrases = [
            "can you show the photo of", "can you show photo of", "can you show the image of",
            "can you show image of", "can you show portrait of", "can you show the portrait of",
            "can you show me the photo of", "can you show me the image of", "can you show me",
            "can you show", "can you give", "show me the photo of", "show me the image of",
            "show the photo of", "show the image of", "show the portrait of", "show photo of",
            "show image of", "show portrait of", "show photos of", "show images of",
            "photo of", "image of", "picture of", "portrait of", "photos of", "images of",
            "pictures of", "portraits of", "along with their photos", "along with photos",
            "with photos", "with photo", "give the photo of", "give photo of", "give image of",
            "give the image of", "please show", "please give", "who is", "who are"
        ]
        used_explicit_person_phrase = False
        for sp in sorted(strip_phrases, key=len, reverse=True):
            if sp in clean_q:
                used_explicit_person_phrase = True
                clean_q = clean_q.replace(sp, " ")

        # Split on conjunctions and punctuation for multi-person queries
        parts = re.split(r'\b(?:and|&|\+|with)\b|,', clean_q)
        extracted = []
        for p in parts:
            p_norm = cls.normalize_name(p)
            # Remove filler words
            tokens = [w for w in p_norm.split() if w not in (
                "the", "a", "an", "of", "for", "in", "at", "to", "on", "from", "by",
                "director", "directors", "board", "member", "members", "person", "people",
                "chairman", "managing", "independent", "whole", "time", "photo", "image",
                "picture", "portrait", "document", "company", "show", "give", "me", "can",
                "you", "please"
            ) and len(w) > 1]
            if tokens:
                cand = " ".join(tokens)
                if len(cand) >= 3 and cand not in extracted:
                    extracted.append(cand)

        # Plausibility gate on the heuristic-extracted candidates: leftover
        # query text after phrase-stripping is only trusted as a PERSON name
        # if it actually corresponds to a real name grounded somewhere in
        # this document's own image registry (`all_known` -- the caller-
        # supplied `known_entities`, e.g. every image chunk's own
        # entity_name; never a fixed roster). Without this, any non-person
        # visual query whose phrasing doesn't match a known
        # strip-phrase (e.g. "show the substation construction site image at
        # Deoghar") gets misread as a person's name and wrongly routed
        # through strict portrait matching instead of general/semantic
        # visual search.
        #
        # When no registry is available at all, fall back to a
        # capitalization-based plausibility signal from the query's OWN
        # original casing (a generic, language-level signal, not tied to any
        # roster): a real proper name is typically capitalized mid-sentence,
        # unlike ordinary descriptive/functional words -- e.g. "What does
        # the architecture diagram show?" has no capitalized word after the
        # sentence-initial "What", so nothing here is trusted as a name.
        #
        # Exception: if the query used an EXPLICIT person-oriented phrase
        # ("photo of X", "who is X", ...), this is unambiguously a person
        # search -- an unrecognised name here must still resolve to a
        # "portrait of someone not in this document" target (zero results),
        # NOT silently fall through to a generic visual search that would
        # incorrectly return unrelated images for e.g. "photo of Elon Musk".
        if not used_explicit_person_phrase:
            if all_known:
                plausible_extracted = []
                for cand in extracted:
                    cand_tokens = set(cand.split())
                    for ent in all_known:
                        ent_norm = cls.normalize_name(ent)
                        ent_tokens = set(ent_norm.split())
                        if not ent_tokens:
                            continue
                        if cand_tokens & ent_tokens:
                            plausible_extracted.append(cand)
                            break
                extracted = plausible_extracted
            else:
                query_words = re.findall(r"\b[A-Za-z]+\b", query)
                capitalized_tokens = {
                    w.lower() for i, w in enumerate(query_words)
                    if i > 0 and w[0].isupper()
                }
                extracted = [cand for cand in extracted if set(cand.split()) & capitalized_tokens]

        # Merge extracted with matched_from_entities
        final_names = []
        for name in (matched_from_entities + extracted):
            norm = cls.normalize_name(name)
            # Avoid a single-token name that's ambiguous WITHIN this
            # document's own registry (shared by 2+ distinct known people) --
            # derived from the document itself, never a fixed surname list.
            if len(norm.split()) == 1 and cls._ambiguous_token_owner_count(norm, all_known) >= 2:
                continue
            if len(norm.split()) >= 1 and len(norm) >= 3 and norm not in final_names:
                final_names.append(norm)

        # If multiple names extracted and one is substring of another, keep the longer/distinct ones
        filtered_names = []
        for n in final_names:
            if not any(n != other and n in other for other in final_names):
                filtered_names.append(n)

        return filtered_names

    @classmethod
    def detect_query_target(cls, query: str, known_entities: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Extracts structured target entity and type information from the query.
        """
        import re
        q_lower = query.lower()

        # 1. Check if pure text query
        if not cls.is_visual_query(query):
            return {"target_type": "pure_text", "is_visual": False}

        # 2. Check Logo Target
        if any(t in q_lower for t in ["logo", "company logo", "brand logo", "emblem", "insignia", "show logo", "show the logo", "give the logo", "give logo"]):
            return {"target_type": "logo", "is_visual": True}

        # 3. Check Board of Directors Collection Target
        if any(t in q_lower for t in ["board of directors", "all directors", "directors and their photos", "directors along with photos", "board members along with", "board along with"]):
            return {"target_type": "board_collection", "is_visual": True}

        # 4. Check Individual & Multi-Director Portrait Target
        extracted_persons = cls.extract_person_names_from_query(query, known_entities=known_entities)
        if len(extracted_persons) > 1:
            return {
                "target_type": "multi_portrait",
                "target_persons": extracted_persons,
                "target_directors": [{"name": p, "variants": [p]} for p in extracted_persons],
                "is_visual": True
            }
        elif len(extracted_persons) == 1:
            return {
                "target_type": "portrait",
                "target_person": extracted_persons[0],
                "target_director": {"name": extracted_persons[0], "variants": [extracted_persons[0]]},
                "is_visual": True
            }

        # 4.1 Check Ambiguous Surname-Only queries (e.g. "photo of Todi"),
        # purely from the document's own known-entity registry: a bare word
        # in the query that's a shared name-part of 2+ distinct known
        # entities, with no extracted candidate resolving it, is ambiguous.
        if known_entities and len(extracted_persons) == 0:
            words = set(re.findall(r'\b[a-zA-Z]+\b', q_lower))
            for w in words:
                if len(w) > 2 and cls._ambiguous_token_owner_count(w, known_entities) >= 2:
                    return {
                        "target_type": "ambiguous_surname",
                        "surname": w,
                        "is_visual": True
                    }

        # 5. Check Captioned Figure Number Target
        fig_match = re.search(r'(?i)\b(?:figure|fig\.?|chart|diagram|image|photo|illustration)\s*#?\s*(\d+)\b', query)
        if fig_match:
            return {
                "target_type": "captioned_figure",
                "figure_number": fig_match.group(1),
                "is_visual": True
            }

        # 6. General visual / diagram / chart target
        return {"target_type": "general_visual", "is_visual": True}

    @classmethod
    def validate_physical_file(cls, image_path: Optional[str] = None, image_url: Optional[str] = None, doc_id: Optional[str] = None) -> bool:
        """
        Validates that the physical image asset actually exists on disk and is non-empty.
        Robustly resolves across absolute paths, relative paths, job output directories, and static URLs.
        """
        from pathlib import Path
        from src.config import ROOT_DIR

        # Check candidate path directly
        if image_path:
            p = Path(image_path)
            if p.exists() and p.is_file() and p.stat().st_size > 0:
                return True
            p_rel = ROOT_DIR / image_path
            if p_rel.exists() and p_rel.is_file() and p_rel.stat().st_size > 0:
                return True

        # Check URL mapped to data/output/
        if image_url and image_url.startswith("/outputs/"):
            rel_parts = image_url.replace("/outputs/", "").split("/")
            if len(rel_parts) >= 2:
                target_disk_path = ROOT_DIR / "data" / "output" / Path("/".join(rel_parts))
                if target_disk_path.exists() and target_disk_path.is_file() and target_disk_path.stat().st_size > 0:
                    return True

        # Check doc_id output folders
        if doc_id and image_path:
            clean_name = Path(str(image_path).replace("\\", "/")).name
            target_disk_path = ROOT_DIR / "data" / "output" / doc_id / "05_images" / clean_name
            if target_disk_path.exists() and target_disk_path.is_file() and target_disk_path.stat().st_size > 0:
                return True
            target_disk_path2 = ROOT_DIR / "data" / "output" / doc_id / clean_name
            if target_disk_path2.exists() and target_disk_path2.is_file() and target_disk_path2.stat().st_size > 0:
                return True

        # Check across any existing run folder if image_path contains 05_images/
        if image_path and "05_images" in str(image_path):
            clean_name = Path(str(image_path).replace("\\", "/")).name
            output_root = ROOT_DIR / "data" / "output"
            if output_root.exists():
                for sub in output_root.iterdir():
                    if sub.is_dir():
                        cand = sub / "05_images" / clean_name
                        if cand.exists() and cand.is_file() and cand.stat().st_size > 0:
                            return True

        return False

    @classmethod
    def validate_single_director_image(
        cls,
        image_meta: Dict[str, Any],
        target_director: Any,
        doc_id: Optional[str] = None
    ) -> bool:
        """
        Generic person portrait validation: validates that an image chunk specifically
        represents the given person or director.
        """
        target_name = ""
        if isinstance(target_director, dict):
            target_name = target_director.get("name", "")
            variants = target_director.get("variants", [target_name])
        else:
            target_name = str(target_director)
            variants = [target_name]

        target_norm = cls.normalize_name(target_name)
        if not target_norm:
            return False

        img_path = image_meta.get("image_path")
        img_url = image_meta.get("image_url")
        if not cls.validate_physical_file(image_path=img_path, image_url=img_url, doc_id=doc_id):
            return False

        # A decorative / non-retrievable / LOW-importance asset can never be
        # someone's portrait, regardless of whether the target's name text
        # happens to appear in its keywords/OCR/semantic description (e.g. a
        # decorative graphic sitting near a paragraph that merely mentions
        # the person). This prevents unrelated images from being returned
        # for a person-portrait query just because of incidental text overlap.
        if (
            str(image_meta.get("image_type") or "").lower() == "decorative"
            or image_meta.get("importance_score") == "LOW"
            or image_meta.get("retrievable") is False
        ):
            return False

        entity_name = cls.normalize_name(image_meta.get("entity_name") or image_meta.get("title") or "")
        caption = cls.normalize_name(image_meta.get("caption") or image_meta.get("caption_text") or "")
        detected_entities = [cls.normalize_name(e) for e in (image_meta.get("detected_entities") or [])]
        people = [cls.normalize_name(p) for p in (image_meta.get("people") or [])]
        keywords = [cls.normalize_name(k) for k in (image_meta.get("keywords") or [])]
        semantic_desc = cls.normalize_name(image_meta.get("semantic_description") or "")

        GENERIC_MIDDLE_NAMES = {"kumar", "chandra", "prasad", "singh", "shri", "smt", "dr", "mr", "mrs", "ms"}
        target_tokens = [w for w in target_norm.split() if w not in GENERIC_MIDDLE_NAMES and len(w) > 2]
        if not target_tokens:
            target_tokens = [w for w in target_norm.split() if len(w) > 2]
        if not target_tokens:
            target_tokens = target_norm.split()

        # Check full string or token match across direct fields
        direct_strings = [entity_name, caption]
        context_strings = [semantic_desc] + detected_entities + people + keywords
        all_meta_strings = direct_strings + context_strings

        # The weak context-only match (keywords/OCR/semantic description
        # mentioning the name, with no entity_name/caption backing it) is
        # only trusted when this image is itself plausibly a person image --
        # otherwise a chart/diagram/logo whose description merely quotes or
        # references the person would incorrectly validate as their portrait.
        img_type_lower = str(image_meta.get("image_type") or "").lower()
        is_plausible_person_image = bool(entity_name) or "portrait" in img_type_lower or img_type_lower in ("photo", "image")

        matches_target = False
        if target_norm in entity_name or target_norm in caption:
            matches_target = True
        elif target_tokens and all(token in entity_name or token in caption for token in target_tokens):
            matches_target = True
        elif is_plausible_person_image and target_tokens and all(any(token in s for s in all_meta_strings if s) for token in target_tokens):
            matches_target = True

        if not matches_target:
            # Check variant matches
            for v in variants:
                v_norm = cls.normalize_name(v)
                v_tokens = [w for w in v_norm.split() if w not in GENERIC_MIDDLE_NAMES and len(w) > 2]
                if v_norm and (v_norm in entity_name or v_norm in caption):
                    matches_target = True
                    break
                elif is_plausible_person_image and v_tokens and all(any(token in s for s in all_meta_strings if s) for token in v_tokens):
                    matches_target = True
                    break

        if not matches_target:
            return False

        # Exclusivity check: reject when entity_name represents a distinct person
        if entity_name:
            e_tokens = [w for w in entity_name.split() if w not in GENERIC_MIDDLE_NAMES and len(w) > 2]
            if e_tokens and target_tokens:
                # If neither the first name nor any distinctive token matches, reject
                has_distinctive_match = any(t in e_tokens for t in target_tokens)
                if not has_distinctive_match:
                    return False
                # If target has distinctive first name and entity has distinctive first name and they differ
                if len(target_tokens) >= 1 and len(e_tokens) >= 1:
                    if target_tokens[0] != e_tokens[0] and target_tokens[0] not in e_tokens and e_tokens[0] not in target_tokens:
                        return False

        return True

    @classmethod
    def validate_image_candidate(
        cls,
        image_meta: Dict[str, Any],
        query: str,
        intent: Optional[str] = None,
        doc_id: Optional[str] = None,
        known_entities: Optional[List[str]] = None
    ) -> bool:
        """
        Executes the complete validation suite on an image candidate:
        query target -> metadata match -> page/layout consistency -> physical file existence -> correct image type.

        `known_entities` should be the current document's OWN registry of
        grounded entity_name values (gathered from its image chunks) so
        query-target classification can tell a real person-name query apart
        from a generic/semantic visual query without hardcoding names.
        """
        # Step 1: Query Target Check
        target_info = cls.detect_query_target(query, known_entities=known_entities)
        if not target_info.get("is_visual", False) or target_info.get("target_type") == "pure_text":
            return False

        # Reject ambiguous surname-only queries (e.g. "photo of Todi")
        if target_info.get("target_type") == "ambiguous_surname":
            logger.info(f"Rejecting image retrieval for ambiguous surname-only query: '{query}'")
            return False

        # Step 2: Physical File Existence Check
        img_path = image_meta.get("image_path")
        img_url = image_meta.get("image_url")
        if not cls.validate_physical_file(image_path=img_path, image_url=img_url, doc_id=doc_id):
            logger.warning(f"Image candidate failed physical file existence validation: {img_path or img_url}")
            return False

        page = int(image_meta.get("page") or image_meta.get("page_number") or 1)
        img_type = (image_meta.get("image_type") or "").lower()
        caption = (image_meta.get("caption") or image_meta.get("caption_text") or "").strip()
        title = (image_meta.get("title") or "").strip()
        target_type = target_info.get("target_type")

        # Step 3: Target-Specific Routing & Validation
        if target_type == "multi_portrait":
            target_persons = target_info.get("target_persons", []) or target_info.get("target_directors", [])
            return any(cls.validate_single_director_image(image_meta, p, doc_id=doc_id) for p in target_persons)

        elif target_type == "portrait":
            target_person = target_info.get("target_person") or target_info.get("target_director")
            if not target_person:
                return False
            return cls.validate_single_director_image(image_meta, target_person, doc_id=doc_id)

        elif target_type == "board_collection":
            # Must be a portrait or leadership figure -- purely content-based
            # (entity/type signal), no fixed page number.
            return bool(image_meta.get("entity_name") or "portrait" in img_type)

        elif target_type == "logo":
            # Must be verified Logo or corporate brand asset, never director portraits
            if "portrait" in img_type or image_meta.get("entity_name"):
                return False
            is_logo_asset = (
                img_type == "logo" or
                "logo" in img_type or
                "logo" in caption.lower() or
                "logo" in title.lower() or
                "logo" in (image_meta.get("semantic_description") or "").lower() or
                any("logo" in str(k).lower() for k in (image_meta.get("keywords") or []))
            )
            return is_logo_asset

        elif target_type == "captioned_figure":
            fig_num = target_info.get("figure_number")
            if fig_num:
                return (
                    fig_num in caption.lower() or
                    fig_num in (image_meta.get("explicit_caption") or "").lower() or
                    fig_num in title.lower() or
                    (image_meta.get("image_id") and fig_num in str(image_meta.get("image_id")))
                )
            return True

        # General visual target: require non-empty visual and physical existence
        if "decorative" in img_type and image_meta.get("importance_score") == "LOW":
            return False
        return True


class ImageProcessor:
    """
    Processes Docling PictureItem elements and saves the images to disk.
    Guarantees physical file extraction on disk with PDF fallback cropping.
    """

    @staticmethod
    def crop_image_from_pdf(
        pdf_path: Path,
        page_number: int,
        bbox: Any,
        target_path: Path,
        dpi: int = 150
    ) -> Optional[str]:
        """
        Renders and crops an image directly from the PDF page using PyMuPDF (fitz).
        Guarantees physical file generation whenever Docling get_image() is unavailable.
        """
        if not pdf_path or not Path(pdf_path).exists() or not bbox:
            return None
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            if page_number < 1 or page_number > len(doc):
                doc.close()
                return None
            page = doc[page_number - 1]
            page_height = page.rect.height

            if isinstance(bbox, dict):
                l, t, r, b = bbox.get("l"), bbox.get("t"), bbox.get("r"), bbox.get("b")
                coord_origin = str(bbox.get("coord_origin") or "BOTTOMLEFT").upper()
            else:
                l = getattr(bbox, "l", None)
                t = getattr(bbox, "t", None)
                r = getattr(bbox, "r", None)
                b = getattr(bbox, "b", None)
                coord_origin = str(getattr(bbox, "coord_origin", "BOTTOMLEFT") or "BOTTOMLEFT").upper()

            if l is None or t is None or r is None or b is None:
                doc.close()
                return None

            if coord_origin == "TOPLEFT":
                y0, y1 = t, b
            else:
                y0, y1 = page_height - t, page_height - b

            x0, x1 = min(l, r), max(l, r)
            y0, y1 = min(y0, y1), max(y0, y1)

            # Ensure valid bounds within page
            rect = fitz.Rect(max(0, x0), max(0, y0), min(page.rect.width, x1), min(page_height, y1))
            if rect.width <= 0 or rect.height <= 0:
                doc.close()
                return None

            target_path = Path(target_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            pix = page.get_pixmap(clip=rect, dpi=dpi)
            pix.save(str(target_path))
            doc.close()
            logger.info(f"Successfully cropped physical image from PDF to {target_path}")
            return str(target_path)
        except Exception as e:
            logger.warning(f"Failed to crop image from PDF {pdf_path}: {e}")
            return None

    @staticmethod
    def process_image(
        element: Any, 
        doc: Any, 
        output_images_dir: Optional[Path] = None,
        pdf_path: Optional[Path] = None
    ) -> ImageMetadata:
        """
        Extracts metadata of an image, saves the cropped image if enabled, and maps captions.
        """
        image_id = element.self_ref
        
        # Get page number
        page_number = 1
        bbox = None
        if hasattr(element, "prov") and element.prov:
            prov = element.prov[0]
            page_number = getattr(prov, "page_no", 1)
            bbox = convert_bbox(getattr(prov, "bbox", None))

        # Extract caption text
        caption_text = CaptionProcessor.extract_caption_text(element, doc)

        # Retrieve and save PIL image if available and output path provided
        image_path_str = None
        if output_images_dir:
            output_images_dir.mkdir(parents=True, exist_ok=True)
            safe_id = image_id.replace("#/", "").replace("/", "_")
            target_path = output_images_dir / f"{safe_id}.png"

            # Primary: retrieve the image bytes/object from Docling
            if hasattr(element, "get_image"):
                try:
                    img = element.get_image(doc)
                    if img:
                        img.save(target_path)
                        image_path_str = str(target_path)
                        logger.info(f"Saved image {image_id} to {target_path}")
                except Exception as e:
                    logger.warning(f"Failed to save image {image_id} via Docling get_image: {e}")

            # Fallback: PyMuPDF crop directly from PDF if get_image was unavailable or failed
            if not image_path_str and pdf_path and bbox:
                image_path_str = ImageProcessor.crop_image_from_pdf(
                    pdf_path=pdf_path,
                    page_number=page_number,
                    bbox=bbox,
                    target_path=target_path
                )

        # OCR text
        ocr_text = None
        if hasattr(element, "text") and element.text:
            ocr_text = element.text

        return ImageMetadata(
            image_id=image_id,
            page_number=page_number,
            bbox=bbox,
            ocr_text=ocr_text,
            caption=caption_text,
            image_path=image_path_str
        )
