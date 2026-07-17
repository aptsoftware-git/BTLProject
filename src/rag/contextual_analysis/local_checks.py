import re
import logging
from typing import List, Dict, Any, Optional
from src.rag.contextual_analysis.models import InconsistencyIssue

logger = logging.getLogger("pipeline")

def text_to_num(text: str) -> Optional[int]:
    """Converts English words for numbers to an integer."""
    words = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
        "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90,
        "hundred": 100, "thousand": 1000, "million": 1000000, "billion": 1000000000
    }
    parts = text.lower().replace("-", " ").split()
    total = 0
    current = 0
    valid = False
    for w in parts:
        if w not in words:
            continue
        valid = True
        val = words[w]
        if val in (100, 1000, 1000000, 1000000000):
            if current == 0:
                current = 1
            current *= val
            if val >= 1000:
                total += current
                current = 0
        else:
            current += val
    return (total + current) if valid else None

class LocalConsistencyChecker:
    """
    Performs deterministic local consistency checks on Knowledge Objects before calling the LLM.
    Reduces unnecessary LLM queries.
    """

    def __init__(self, page_count: int = 1):
        self.page_count = page_count

    def check_all(self, objects: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        issues = []
        issues.extend(self.check_numeric_parentheses_mismatches(objects))
        issues.extend(self.check_section_numbering_gaps(objects))
        issues.extend(self.check_broken_page_references(objects))
        issues.extend(self.check_duplicate_headings(objects))
        issues.extend(self.check_broken_section_references(objects))
        issues.extend(self.check_date_mismatches(objects))
        issues.extend(self.check_formatting_inconsistencies(objects))
        return issues

    def check_broken_section_references(self, objects: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        """Detects references to non-existent sections (e.g. 'See Section 6.2' when Section 6.2 doesn't exist)."""
        issues = []
        headings = [o for o in objects if o.get("chunk_type") == "Heading"]
        
        # 1. Collect all existing heading numbers
        outline_pattern = re.compile(r'^(\d+(?:\.\d+)*)\b')
        existing_sections = set()
        for h in headings:
            text = h.get("text", "").strip()
            match = outline_pattern.match(text)
            if match:
                existing_sections.add(match.group(1))
                
        if not existing_sections:
            return issues
            
        # 2. Find section references in text
        ref_pattern = re.compile(r'\b(?:Section|Sec\.?)\s*(\d+(?:\.\d+)+)\b', re.IGNORECASE)
        for obj in objects:
            text = obj.get("text", "")
            matches = ref_pattern.finditer(text)
            for match in matches:
                ref_sec = match.group(1)
                if ref_sec not in existing_sections:
                    issues.append(InconsistencyIssue(
                        category="Reference Conflict",
                        severity="High",
                        confidence=0.9,
                        description=f"Broken section reference: text refers to Section {ref_sec}, but Section {ref_sec} does not exist in the document.",
                        evidence=match.group(0),
                        object_ids=[obj.get("knowledge_id")],
                        page_numbers=[obj.get("page_number", 1)],
                        section_path=obj.get("section_path", "Root"),
                        quoted_text=match.group(0)
                    ))
        return issues

    def check_numeric_parentheses_mismatches(self, objects: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        """Detects mismatches like: "One thousand five hundred (10005)"."""
        issues = []
        # Match words followed by parenthesis numbers
        # e.g., "one hundred (1000)" or "five thousand (50)"
        pattern = re.compile(r'\b([a-zA-Z\-\s]+)\s*\((\d+)\)')
        
        for obj in objects:
            text = obj.get("text", "")
            matches = pattern.finditer(text)
            for match in matches:
                word_part = match.group(1).strip()
                digit_part = int(match.group(2).strip())
                
                # Check if it looks like number words
                parsed_num = text_to_num(word_part)
                if parsed_num is not None and parsed_num != digit_part:
                    # Filter out standard non-number text sequences
                    if any(term in word_part.lower() for term in ["section", "page", "chapter", "figure", "table"]):
                        continue
                        
                    issues.append(InconsistencyIssue(
                        category="Numeric Mismatch",
                        severity="High",
                        confidence=0.95,
                        description=f"Numeric mismatch detected: Words '{word_part}' represents value {parsed_num}, but parenthesis contains digits '{digit_part}'.",
                        evidence=match.group(0),
                        object_ids=[obj.get("knowledge_id")],
                        page_numbers=[obj.get("page_number", 1)],
                        section_path=obj.get("section_path", "Root"),
                        quoted_text=match.group(0),
                        metadata={"type": "parenthesis_mismatch", "words_val": parsed_num, "digits_val": digit_part}
                    ))
        return issues

    def check_section_numbering_gaps(self, objects: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        """Detects sequence gaps in headings (e.g. 1.1 followed by 1.3)."""
        issues = []
        headings = [o for o in objects if o.get("chunk_type") == "Heading"]
        
        # Regex to match numeric outline prefixes like "1.2", "2.1.3", "Section 3"
        outline_pattern = re.compile(r'^(\d+(?:\.\d+)*)\b')
        
        last_nums: List[int] = []
        last_heading_id = None
        last_heading_text = ""
        
        for h in headings:
            text = h.get("text", "").strip()
            match = outline_pattern.match(text)
            if not match:
                continue
                
            num_str = match.group(1)
            nums = [int(x) for x in num_str.split(".")]
            
            if last_nums:
                # Compare same level sequence numbering
                common_len = min(len(last_nums), len(nums))
                # Check if prefix matches up to common parent
                if last_nums[:common_len-1] == nums[:common_len-1]:
                    level = common_len - 1
                    diff = nums[level] - last_nums[level]
                    if diff > 1:
                        issues.append(InconsistencyIssue(
                            category="Reference Conflict",
                            severity="Medium",
                            confidence=0.85,
                            description=f"Out of sequence section numbering. Section '{text}' follows '{last_heading_text}', leaving a numbering gap.",
                            evidence=f"Section numbering jump from {last_nums} to {nums}",
                            object_ids=[last_heading_id, h.get("knowledge_id")] if last_heading_id else [h.get("knowledge_id")],
                            page_numbers=[h.get("page_number", 1)],
                            section_path=h.get("section_path", "Root"),
                            quoted_text=text
                        ))
            last_nums = nums
            last_heading_id = h.get("knowledge_id")
            last_heading_text = text
            
        return issues

    def check_broken_page_references(self, objects: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        """Detects page references that point to non-existent pages (e.g., page 5 in a 3-page doc)."""
        issues = []
        pattern = re.compile(r'\b(?:page|pg\.?)\s*(\d+)\b', re.IGNORECASE)
        
        for obj in objects:
            text = obj.get("text", "")
            matches = pattern.finditer(text)
            for match in matches:
                target_page = int(match.group(1))
                if target_page > self.page_count:
                    issues.append(InconsistencyIssue(
                        category="Reference Conflict",
                        severity="Medium",
                        confidence=0.9,
                        description=f"Broken page reference: text refers to page {target_page}, but the document only has {self.page_count} page(s).",
                        evidence=match.group(0),
                        object_ids=[obj.get("knowledge_id")],
                        page_numbers=[obj.get("page_number", 1)],
                        section_path=obj.get("section_path", "Root"),
                        quoted_text=match.group(0)
                    ))
        return issues

    def check_duplicate_headings(self, objects: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        """Detects duplicate section headings in the same level."""
        issues = []
        headings = [o for o in objects if o.get("chunk_type") == "Heading"]
        
        seen_headings: Dict[str, List[Dict[str, Any]]] = {}
        for h in headings:
            text = h.get("text", "").strip().lower()
            if not text or len(text) < 4:
                continue
            parent = h.get("parent_heading") or "Root"
            key = f"{parent} > {text}"
            
            if key in seen_headings:
                seen_headings[key].append(h)
            else:
                seen_headings[key] = [h]
                
        for key, dup_list in seen_headings.items():
            if len(dup_list) > 1:
                first = dup_list[0]
                last = dup_list[-1]
                parent = first.get("parent_heading") or "Root"
                if first.get("knowledge_id") != last.get("knowledge_id"):
                    issues.append(InconsistencyIssue(
                        category="Terminology Inconsistency",
                        severity="Low",
                        confidence=0.75,
                        description=f"Duplicate section heading '{first.get('text')}' detected under parent section '{parent}'.",
                        evidence=f"Heading '{first.get('text')}' duplicated on page {first.get('page_number')} and page {last.get('page_number')}",
                        object_ids=[first.get("knowledge_id"), last.get("knowledge_id")],
                        page_numbers=[first.get("page_number"), last.get("page_number")],
                        section_path=first.get("section_path", "Root"),
                        quoted_text=first.get("text")
                    ))
        return issues

    def check_date_mismatches(self, objects: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        """Detects date/year discrepancies for the same named milestone or event."""
        issues = []
        patterns = [
            (re.compile(r'\b(?:effective|expiration|commencement|start|end|completion|termination|signing|agreement)\s+date\s+(?:is|of|from|on|to)?\s*([A-Z][a-z]+ \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})\b', re.IGNORECASE), "date"),
            (re.compile(r'\b(?:FY\s*20\d{2}|FY\s*\d{2})\s+revenue\s+(?:was|is|of)?\s*(?:\$|Rs\.?|INR)?\s*(\d+(?:\.\d+)?\s*(?:million|billion|crore|lakh)?)\b', re.IGNORECASE), "FY revenue")
        ]
        
        seen_events: Dict[str, List[Tuple[Dict[str, Any], str]]] = {}
        for obj in objects:
            text = obj.get("text", "")
            for pattern, event_type in patterns:
                matches = pattern.finditer(text)
                for m in matches:
                    full_match_text = m.group(0)
                    extracted_value = m.group(1).strip()
                    context_key = full_match_text.replace(extracted_value, "").strip().lower()
                    context_key = re.sub(r'[\s\W]+', ' ', context_key).strip()
                    
                    if context_key:
                        seen_events.setdefault(context_key, []).append((obj, extracted_value))
                        
        for context, occurrences in seen_events.items():
            if len(occurrences) > 1:
                first_obj, first_val = occurrences[0]
                for other_obj, other_val in occurrences[1:]:
                    if first_val.lower() != other_val.lower() and first_obj.get("knowledge_id") != other_obj.get("knowledge_id"):
                        issues.append(InconsistencyIssue(
                            category="Date Conflicts" if "date" in context else "Numeric Mismatch",
                            severity="High",
                            confidence=0.92,
                            description=f"Conflicting statement details for '{context}': '{first_val}' (Page {first_obj.get('page_number')}) vs. '{other_val}' (Page {other_obj.get('page_number')}).",
                            evidence=f"Value discrepancy: '{first_val}' vs '{other_val}'",
                            object_ids=[first_obj.get("knowledge_id"), other_obj.get("knowledge_id")],
                            page_numbers=[first_obj.get("page_number"), other_obj.get("page_number")],
                            section_path=first_obj.get("section_path", "Root"),
                            quoted_text=f"{context} {first_val}"
                        ))
        return issues

    def check_formatting_inconsistencies(self, objects: List[Dict[str, Any]]) -> List[InconsistencyIssue]:
        """Detects formatting notation scale system mixing (e.g. mixing Crore/Lakh with Western Million/Billion scale)."""
        issues = []
        has_indian_notation = False
        has_western_notation = False
        
        indian_nodes = []
        western_nodes = []
        
        for obj in objects:
            text = obj.get("text", "").lower()
            if any(term in text for term in ["crore", "lakh"]):
                has_indian_notation = True
                indian_nodes.append(obj)
            if any(term in text for term in ["million", "billion"]):
                has_western_notation = True
                western_nodes.append(obj)
                
        if has_indian_notation and has_western_notation:
            first_ind = indian_nodes[0]
            first_west = western_nodes[0]
            issues.append(InconsistencyIssue(
                category="Terminology Inconsistency",
                severity="Low",
                confidence=0.8,
                description="Inconsistent metric notation systems: document mixes Indian numbering scale (Crore/Lakh) with Western scale (Million/Billion).",
                evidence="Indian scale notation found on page " + str(first_ind.get("page_number")) + ", Western scale notation on page " + str(first_west.get("page_number")),
                object_ids=[first_ind.get("knowledge_id"), first_west.get("knowledge_id")],
                page_numbers=[first_ind.get("page_number"), first_west.get("page_number")],
                section_path=first_ind.get("section_path", "Root"),
                quoted_text="crore/lakh vs million/billion"
            ))
        return issues
