"""
entity_linker.py
=================
Generic, document-scoped person/entity resolution and linking.

Connects a portrait's grounded identity (entity_name/designation, however it
was resolved -- explicit_caption, same_card_layout, ocr_grounded_identity,
signature_text_grounded, or spatial_document_context) to the actual text
chunks that discuss that same person: biography, qualifications, experience,
designation. This is what lets a "what are X's qualifications?" query be
answered from real document prose instead of the portrait's own short
metadata, while a pure portrait-photo query still resolves to the image and
nothing else.

Fully generic: an entity_id is derived purely from the person's own name as
already grounded from real document text (never a fixed roster, never a
hardcoded name/page/document rule). Runs once per document, after chunk
building/indexing and after duplicate-image cleanup, so it links against the
final, de-duplicated chunk set.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("pipeline")

# Ordinary English honorifics -- never a specific person's name -- stripped
# when computing a stable entity key so "Mr. Ravi Todi" and "Ravi Todi"
# resolve to the same person.
_HONORIFIC_PREFIXES = (
    "mr.", "mr ", "mrs.", "mrs ", "ms.", "ms ", "dr.", "dr ",
    "shri ", "smt ", "er.", "er ", "prof.", "prof ", "m/s.", "m/s ",
)


def normalize_entity_text(name: Optional[str]) -> str:
    """Generic name normalization: strip honorifics/punctuation, collapse whitespace, lowercase."""
    if not name:
        return ""
    n = str(name).strip().lower()
    for prefix in _HONORIFIC_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def generate_entity_key(document_id: str, entity_name: Optional[str]) -> Optional[str]:
    """Stable, document-scoped entity id derived purely from the grounded name."""
    norm = normalize_entity_text(entity_name)
    if not norm:
        return None
    return f"{document_id}_entity_{norm.replace(' ', '_')}"


def _name_tokens(entity_name: str) -> List[str]:
    return [t for t in normalize_entity_text(entity_name).split() if len(t) > 1]


def chunk_mentions_entity(chunk_text: Optional[str], entity_name: Optional[str]) -> bool:
    """
    Generic "does this chunk discuss this person" check: the chunk's own
    normalized text must contain either the full normalized name as a
    contiguous phrase, or every significant name token (so real-prose word
    order/punctuation differences don't cause a miss). Matched purely
    against the chunk's own real content -- never a fixed roster.
    """
    if not chunk_text or not entity_name:
        return False
    norm_chunk = normalize_entity_text(chunk_text)
    norm_name = normalize_entity_text(entity_name)
    if not norm_name or not norm_chunk:
        return False
    if norm_name in norm_chunk:
        return True
    tokens = _name_tokens(entity_name)
    if len(tokens) >= 2 and all(re.search(rf"\b{re.escape(t)}\b", norm_chunk) for t in tokens):
        return True
    return False


def link_entities_across_chunks(chunks: List[Dict[str, Any]], document_id: str) -> Dict[str, int]:
    """
    Given the FULL flat list of a document's chunk dicts (as persisted in
    document_chunks.json -- {"content": ..., "metadata": {...}}), for every
    image chunk with a grounded entity_name:
      1. Computes a stable entity_id from that name.
      2. Finds every non-image chunk whose own text mentions the same
         person (generic substring/token matching -- never a fixed roster).
      3. Stamps entity_id on both the image chunk and every matched text
         chunk (entity_ids holds every person a shared/overlap text chunk
         mentions), and stamps linked_text_chunk_ids on the image chunk.
    Mutates the chunk dicts in place. Returns counts for logging.
    """
    stats = {"portraits_linked": 0, "text_chunks_linked": 0}
    if not chunks:
        return stats

    image_chunks = [
        c for c in chunks
        if (c.get("metadata") or {}).get("chunk_type") == "image"
        and (c.get("metadata") or {}).get("entity_name")
    ]
    if not image_chunks:
        return stats

    text_chunks = [c for c in chunks if (c.get("metadata") or {}).get("chunk_type") != "image"]
    text_chunk_entities: Dict[str, set] = {}
    # Reverse direction of linked_text_chunk_ids: which image(s) depict a
    # given entity, so a text-only query ("What are X's qualifications?")
    # can also surface the associated portrait, not just the other way
    # around -- see link_person_entities_for_document's docstring.
    entity_to_image_ids: Dict[str, set] = {}

    for img_chunk in image_chunks:
        meta = img_chunk.setdefault("metadata", {})
        entity_name = meta.get("entity_name")
        entity_key = generate_entity_key(document_id, entity_name)
        if not entity_key:
            continue

        meta["entity_id"] = entity_key
        image_id = meta.get("image_id")
        if image_id:
            entity_to_image_ids.setdefault(entity_key, set()).add(image_id)

        linked_ids: List[str] = []
        for t_chunk in text_chunks:
            t_meta = t_chunk.get("metadata") or {}
            t_chunk_id = t_meta.get("chunk_id")
            if not t_chunk_id:
                continue
            content = t_chunk.get("content") or ""
            if chunk_mentions_entity(content, entity_name):
                linked_ids.append(t_chunk_id)
                text_chunk_entities.setdefault(t_chunk_id, set()).add(entity_key)
                stats["text_chunks_linked"] += 1

        meta["linked_text_chunk_ids"] = sorted(set(linked_ids))
        if meta["linked_text_chunk_ids"]:
            stats["portraits_linked"] += 1

        logger.info(
            "[entity_linker] portrait chunk=%s entity_id=%s entity_name=%s designation=%s "
            "-> linked %d text chunk(s): %s",
            meta.get("chunk_id"), entity_key, entity_name, meta.get("designation"),
            len(meta["linked_text_chunk_ids"]), meta["linked_text_chunk_ids"],
        )

    # Stamp the resolved entity id(s), and every image depicting them, onto
    # each matched text chunk, deterministically.
    for t_chunk in text_chunks:
        t_meta = t_chunk.get("metadata") or {}
        t_chunk_id = t_meta.get("chunk_id")
        keys = text_chunk_entities.get(t_chunk_id)
        if not keys:
            continue
        ordered = sorted(keys)
        t_meta["entity_ids"] = ordered
        t_meta["entity_id"] = ordered[0]
        linked_image_ids = sorted({img_id for key in keys for img_id in entity_to_image_ids.get(key, ())})
        if linked_image_ids:
            t_meta["linked_image_ids"] = linked_image_ids

    return stats


def _load_chunks_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[entity_linker] Failed to read chunks file {path}: {e}")
        return None


def _write_chunks_file(path: Path, data: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"[entity_linker] Failed to write chunks file {path}: {e}")


def link_person_entities_for_document(
    output_dir: Path,
    document_id: str,
    vector_store: Optional[Any] = None,
) -> Dict[str, int]:
    """
    Final document-scoped pass: resolves each grounded portrait's identity
    into a stable entity_id, links it to every text chunk that actually
    discusses that person, and persists the link on all three surfaces --
    the chunk list (document_chunks.json, both copies), the image's own JSON
    metadata (05_images/*.json), and (if already embedded) the vector DB
    record's metadata.
    """
    output_dir = Path(output_dir)
    chunk_paths = [
        output_dir / "document_chunks.json",
        output_dir / "06_chunks" / "document_chunks.json",
    ]

    total_stats = {"portraits_linked": 0, "text_chunks_linked": 0}
    touched_chunk_updates: Dict[str, Dict[str, Any]] = {}
    image_entity_updates: Dict[str, Dict[str, Any]] = {}

    for chunks_path in chunk_paths:
        data = _load_chunks_file(chunks_path)
        if not data or not isinstance(data.get("chunks"), list):
            continue

        stats = link_entities_across_chunks(data["chunks"], document_id)
        total_stats["portraits_linked"] = max(total_stats["portraits_linked"], stats["portraits_linked"])
        total_stats["text_chunks_linked"] = max(total_stats["text_chunks_linked"], stats["text_chunks_linked"])

        for chunk in data["chunks"]:
            meta = chunk.get("metadata") or {}
            chunk_id = meta.get("chunk_id")
            if not chunk_id:
                continue
            if meta.get("chunk_type") == "image" and meta.get("entity_id"):
                touched_chunk_updates[chunk_id] = {
                    "entity_id": meta["entity_id"],
                    "linked_text_chunk_ids": json.dumps(meta.get("linked_text_chunk_ids", [])),
                }
                img_id = meta.get("image_id")
                if img_id:
                    image_entity_updates[img_id] = {
                        "entity_id": meta["entity_id"],
                        "linked_text_chunk_ids": meta.get("linked_text_chunk_ids", []),
                    }
            elif meta.get("entity_id"):
                touched_chunk_updates[chunk_id] = {
                    "entity_id": meta["entity_id"],
                    "entity_ids": json.dumps(meta.get("entity_ids", [])),
                    "linked_image_ids": json.dumps(meta.get("linked_image_ids", [])),
                }

        _write_chunks_file(chunks_path, data)

    # Patch 05_images/*.json so the image's own persisted metadata carries
    # the same entity_id/linked_text_chunk_ids as its chunk record.
    images_dir = output_dir / "05_images"
    if image_entity_updates and images_dir.exists():
        for jf in images_dir.glob("image_*.json"):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    jd = json.load(f)
            except Exception as e:
                logger.warning(f"[entity_linker] Failed to read image JSON {jf.name}: {e}")
                continue
            img_id = jd.get("image_id")
            update = image_entity_updates.get(img_id)
            if not update:
                continue
            jd["entity_id"] = update["entity_id"]
            jd["linked_text_chunk_ids"] = update["linked_text_chunk_ids"]
            try:
                with open(jf, "w", encoding="utf-8") as f:
                    json.dump(jd, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"[entity_linker] Failed to write image JSON {jf.name}: {e}")

    # Push the same fields into the already-indexed vector DB records so
    # retrieval sees them without requiring a full re-embed.
    if touched_chunk_updates and vector_store is not None:
        try:
            updated = vector_store.update_chunk_metadata(document_id, touched_chunk_updates)
            logger.info(f"[entity_linker] Updated {updated} vector DB record(s) with entity links for {document_id}.")
        except Exception as e:
            logger.warning(f"[entity_linker] Failed to update vector DB entity metadata for {document_id}: {e}")

    logger.info(
        "[entity_linker] Entity linking summary for %s | portraits linked: %d -> text chunks linked: %d",
        document_id, total_stats["portraits_linked"], total_stats["text_chunks_linked"],
    )
    return total_stats
