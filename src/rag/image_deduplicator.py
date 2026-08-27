import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger("pipeline")

# 16x16 difference-hash -> 256-bit fingerprint. Purely pixel-content based,
# no document-specific rules: resistant to minor resize/recompression so
# repeated logos/headers/footers/decorative assets hash close together,
# while genuinely different images (even in the same visual category, e.g.
# two distinct portraits) hash far apart.
HASH_SIZE = 16
NEAR_DUP_HAMMING_THRESHOLD = 6  # out of 256 bits (~2.3%) -- near-identical only


def compute_phash(image_path: Path, hash_size: int = HASH_SIZE) -> Optional[int]:
    """Generic content-based perceptual (difference) hash computed from pixels only."""
    try:
        with Image.open(image_path) as img:
            gray = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
            pixels = list(gray.getdata())
            bits = 0
            for row in range(hash_size):
                row_offset = row * (hash_size + 1)
                for col in range(hash_size):
                    left = pixels[row_offset + col]
                    right = pixels[row_offset + col + 1]
                    bits = (bits << 1) | (1 if left > right else 0)
            return bits
    except Exception as e:
        logger.warning(f"Failed to compute perceptual hash for {image_path}: {e}")
        return None


def compute_exact_hash(image_path: Path) -> Optional[str]:
    """Byte-exact SHA-256 hash for detecting identical copies."""
    try:
        h = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        logger.warning(f"Failed to compute exact hash for {image_path}: {e}")
        return None


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def image_quality_score(image_path: Path) -> Tuple[int, int]:
    """
    Generic, content-based quality proxy: (pixel area, file size). Larger,
    higher-resolution, more detailed files win as the canonical copy --
    no document-specific heuristics involved.
    """
    area = 0
    try:
        with Image.open(image_path) as img:
            area = img.width * img.height
    except Exception:
        pass
    size = 0
    try:
        size = image_path.stat().st_size
    except Exception:
        pass
    return (area, size)


class ImageDeduplicationRegistry:
    """
    Incremental, content-based duplicate-image detector used DURING streaming
    extraction so a repeated logo/header/footer/decorative asset (or any
    exact/near-exact repeat) never reaches chunking or vector-DB indexing.

    Purely pixel-content based (exact SHA-256 + perceptual dHash) -- never
    keyed on document-specific text, page ranges, or category labels, so
    genuinely different images are never merged just because they look
    similar in category (e.g. two different director portraits, two
    different charts).
    """

    def __init__(self, near_dup_threshold: int = NEAR_DUP_HAMMING_THRESHOLD):
        self.near_dup_threshold = near_dup_threshold
        self._exact_index: Dict[str, str] = {}          # sha256 -> canonical seq_name
        self._phash_index: List[Tuple[int, str]] = []    # (phash, canonical seq_name)
        self._quality: Dict[str, Tuple[int, int]] = {}   # seq_name -> (area, size)
        self.total_seen = 0
        self.duplicates_removed = 0

    def check_and_register(self, image_path: Path, seq_name: str) -> Optional[str]:
        """
        Registers a newly saved candidate image. Returns the canonical
        seq_name it duplicates (None if this image is itself unique and
        becomes the new canonical). When the candidate is higher quality
        than the existing canonical, upgrades the canonical's pixel file
        in place (same filename, better content) so the highest-quality
        copy is always what gets retrieved/displayed.
        """
        self.total_seen += 1
        exact_hash = compute_exact_hash(image_path)
        phash = compute_phash(image_path)

        canonical_seq = None
        if exact_hash and exact_hash in self._exact_index:
            canonical_seq = self._exact_index[exact_hash]
        elif phash is not None:
            for existing_phash, existing_seq in self._phash_index:
                if hamming_distance(phash, existing_phash) <= self.near_dup_threshold:
                    canonical_seq = existing_seq
                    break

        if canonical_seq is None:
            if exact_hash:
                self._exact_index[exact_hash] = seq_name
            if phash is not None:
                self._phash_index.append((phash, seq_name))
            self._quality[seq_name] = image_quality_score(image_path)
            return None

        self.duplicates_removed += 1

        # Highest-quality-canonical rule: upgrade in place if this dup is better.
        candidate_quality = image_quality_score(image_path)
        canonical_quality = self._quality.get(canonical_seq, (0, 0))
        if candidate_quality > canonical_quality:
            self._quality[canonical_seq] = candidate_quality
            try:
                canonical_png = image_path.parent / f"{canonical_seq}.png"
                canonical_png.write_bytes(image_path.read_bytes())
                logger.info(
                    f"Upgraded canonical image {canonical_seq} with higher-quality duplicate "
                    f"content ({candidate_quality} > {canonical_quality})."
                )
            except Exception as e:
                logger.warning(f"Failed to upgrade canonical image {canonical_seq}: {e}")

        return canonical_seq

    def summary(self) -> Dict[str, int]:
        return {
            "total_extracted": self.total_seen,
            "duplicates_removed": self.duplicates_removed,
            "unique_retained": self.total_seen - self.duplicates_removed,
        }


def merge_duplicate_page_into_canonical(
    canonical_json_path: Path,
    duplicate_page_number: int,
    duplicate_image_id: Optional[str] = None,
) -> None:
    """
    Merges a duplicate image's source-page information into the canonical
    image's already-persisted JSON metadata, so the canonical entry records
    every page the visual asset actually appeared on.
    """
    import json

    if not canonical_json_path.exists():
        return
    try:
        with open(canonical_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read canonical image metadata {canonical_json_path}: {e}")
        return

    source_pages = set(data.get("source_pages") or [data.get("page")])
    source_pages.add(duplicate_page_number)
    data["source_pages"] = sorted(p for p in source_pages if p is not None)
    data["duplicate_count"] = int(data.get("duplicate_count") or 0) + 1
    if duplicate_image_id:
        dup_ids = set(data.get("duplicate_image_ids") or [])
        dup_ids.add(duplicate_image_id)
        data["duplicate_image_ids"] = sorted(dup_ids)

    try:
        with open(canonical_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to update canonical image metadata {canonical_json_path}: {e}")
