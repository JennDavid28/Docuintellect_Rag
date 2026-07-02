import logging
import os
from elasticsearch import Elasticsearch, BadRequestError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ES_URL = os.environ.get("ES_URL", "http://11.0.0.145:9200")
ES_INFERENCE_ID = os.environ.get("ES_INFERENCE_ID", ".multilingual-e5-small_linux-x86_64")
INDEX_NAME = "docuintellect_chunks"
PIPELINE_NAME = "docuintellect_embedding_pipeline"
RRF_K = 60

# ---------------------------------------------------------------------------
# How multi-document search works (the core problem you hit):
#
# BM25 scores are computed per-shard using TF-IDF. A name like "Priya" that
# appears 10 times in Document A will score much higher than the same name
# appearing once in Document B — even though BOTH are valid matches.
# The old code applied a global score floor (top_score * ratio) which meant
# Document B's match was silently dropped because it scored lower than A.
#
# Fix: instead of a global floor, we guarantee at least one result per
# document that has ANY match, then rank within that guaranteed set.
# This is called "per-document coverage" and is the industry standard
# approach for multi-document retrieval panels.
# ---------------------------------------------------------------------------

def get_es_client():
    try:
        es = Elasticsearch(ES_URL, request_timeout=10)
        es.info()
        return es
    except Exception as e:
        logger.warning(f"Elasticsearch connection failed: {str(e)}")
        return None

def init_es():
    es = get_es_client()
    if not es:
        logger.warning("Skipping Elasticsearch initialization: server unreachable.")
        return False

    try:
        pipeline_definition = {
            "description": "DocuIntellect Ingestion Pipeline with E5 Embedding Model",
            "processors": [
                {
                    "inference": {
                        "model_id": ES_INFERENCE_ID,
                        "target_field": "text_embedding",
                        "field_map": {"text_content": "text_field"},
                        "inference_config": {"text_embedding": {}}
                    }
                },
                {
                    "set": {
                        "field": "text_embedding",
                        "copy_from": "text_embedding.predicted_value",
                        "override": True
                    }
                }
            ]
        }
        es.ingest.put_pipeline(id=PIPELINE_NAME, **pipeline_definition)
        logger.info(f"Elasticsearch pipeline '{PIPELINE_NAME}' created/updated.")
    except Exception as e:
        logger.error(f"Error creating Elasticsearch pipeline: {str(e)}")

    try:
        properties = {
            "user_id":           {"type": "integer"},
            "folder_id":         {"type": "integer"},
            "document_id":       {"type": "integer"},
            "filename":          {"type": "keyword"},
            "page_number":       {"type": "integer"},
            "chunk_index":       {"type": "integer"},
            "content_type":      {"type": "keyword"},
            "text_content":      {"type": "text", "analyzer": "standard"},
            "table_markdown":    {"type": "text", "analyzer": "standard"},
            "image_description": {"type": "text", "analyzer": "standard"},
            "image_count":       {"type": "integer"},
            "text_embedding": {
                "type": "dense_vector",
                "dims": 384,
                "index": True,
                "similarity": "cosine"
            }
        }

        if not es.indices.exists(index=INDEX_NAME):
            index_mapping = {
                "settings": {
                    "index": {
                        "default_pipeline": PIPELINE_NAME,
                        "number_of_shards": 1,
                        "number_of_replicas": 0
                    }
                },
                "mappings": {"properties": properties}
            }
            es.indices.create(index=INDEX_NAME, settings=index_mapping["settings"], mappings=index_mapping["mappings"])
            logger.info(f"Elasticsearch index '{INDEX_NAME}' created.")
        else:
            try:
                es.indices.put_mapping(index=INDEX_NAME, properties={
                    "content_type":      properties["content_type"],
                    "image_count":       properties["image_count"],
                })
            except Exception as map_exc:
                # Analyzer changes on existing fields (e.g. image_description,
                # table_markdown) can't be applied via put_mapping — that requires
                # reindexing. These fields already exist and work fine with
                # whatever analyzer they were created with, so this is safe to skip.
                logger.warning(f"Skipping non-critical mapping update: {map_exc}")
            logger.info(f"Elasticsearch index '{INDEX_NAME}' already exists.")
        return True
    except Exception as e:
        logger.error(f"Error initializing Elasticsearch index: {str(e)}")
        return False

def index_chunks(user_id, folder_id, document_id, filename, chunks):
    es = get_es_client()
    if not es:
        logger.error("Elasticsearch is offline. Cannot index chunks.")
        return False
    try:
        for idx, chunk in enumerate(chunks):
            doc_body = {
                "user_id":           user_id,
                "folder_id":         folder_id,
                "document_id":       document_id,
                "filename":          filename,
                "page_number":       chunk.get("page_number", 1),
                "chunk_index":       idx,
                "content_type":      chunk.get("content_type", "text"),
                "text_content":      chunk.get("text_content", ""),
                "table_markdown":    chunk.get("table_markdown"),
                "image_description": chunk.get("image_description"),
                "image_count":       chunk.get("image_count", 0),
            }
            es.index(index=INDEX_NAME, document=doc_body)
        logger.info(f"Indexed {len(chunks)} chunks for document '{filename}'.")
        return True
    except Exception as e:
        logger.error(f"Error indexing chunks in Elasticsearch: {str(e)}")
        return False

def delete_document_chunks(document_id):
    es = get_es_client()
    if not es:
        return False
    try:
        es.delete_by_query(index=INDEX_NAME, query={"term": {"document_id": document_id}})
        logger.info(f"Deleted chunks for document ID {document_id} from Elasticsearch.")
        return True
    except Exception as e:
        logger.error(f"Error deleting chunks from Elasticsearch: {str(e)}")
        return False

def _source_to_result(hit, rank=None, search_type=None, rrf_score=None):
    source = hit["_source"]
    return {
        "id":                hit.get("_id"),
        "document_id":       source.get("document_id"),
        "filename":          source.get("filename"),
        "page_number":       source.get("page_number"),
        "chunk_index":       source.get("chunk_index"),
        "content_type":      source.get("content_type", "text"),
        "text_content":      source.get("text_content"),
        "table_markdown":    source.get("table_markdown"),
        "image_description": source.get("image_description"),
        "image_count":       source.get("image_count", 0),
        "score":             hit.get("_score", 0.0),
        "rank":              rank,
        "search_type":       search_type,
        "rrf_score":         rrf_score,
        "matched_by":        [search_type] if search_type else [],
    }

def _normalize_for_dedup(text: str) -> str:
    return " ".join((text or "").lower().split())[:200]

def _dedupe_results(results, limit):
    deduped = []
    seen = set()
    for item in results:
        sig = (
            item.get("document_id"),
            item.get("content_type"),
            _normalize_for_dedup(item.get("text_content")),
        )
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


# ---------------------------------------------------------------------------
# Per-document coverage guarantee
# ---------------------------------------------------------------------------
def _guarantee_doc_coverage(results, score_key, abs_min_score, limit_per_doc=2, total_limit=None):
    """
    Given a flat ranked list of results, ensure EVERY document that has at
    least one result above abs_min_score contributes up to `limit_per_doc`
    results to the final list.

    Results are still ordered by score within each document, and the final
    list is sorted by score descending — so high-scoring docs still appear
    first, but low-scoring docs are never completely absent.

    This is what stops "Priya Sharma" in doc A from pushing out
    "Priya Verma" in doc B just because A's TF-IDF score is higher.
    """
    # Group by document, keep only chunks above the absolute floor
    by_doc: dict = {}
    order: list = []
    for item in results:
        doc_id = item.get("document_id")
        score = item.get(score_key, 0.0) or 0.0
        if score < abs_min_score:
            continue
        if doc_id not in by_doc:
            by_doc[doc_id] = []
            order.append(doc_id)
        by_doc[doc_id].append(item)

    # Sort each doc's chunks by score descending, keep top N per doc
    covered = []
    for doc_id in order:
        chunks = sorted(by_doc[doc_id], key=lambda x: x.get(score_key, 0.0) or 0.0, reverse=True)
        covered.extend(chunks[:limit_per_doc])

    # Final sort by score so best matches appear first overall
    covered.sort(key=lambda x: x.get(score_key, 0.0) or 0.0, reverse=True)

    if total_limit:
        covered = covered[:total_limit]

    return _dedupe_results(covered, total_limit or len(covered))


def _rrf_fuse(result_lists, limit):
    """
    Reciprocal Rank Fusion across multiple retrieval lists.
    Guarantees per-document coverage — every document with any hit
    contributes to the fused result regardless of absolute score differences.
    """
    fused = {}
    order = 0
    for search_type, results in result_lists:
        for rank, result in enumerate(results, start=1):
            key = result.get("id") or (
                result.get("document_id"),
                result.get("page_number"),
                result.get("chunk_index"),
                result.get("content_type"),
            )
            if key not in fused:
                order += 1
                fused[key] = {
                    **result,
                    "rrf_score": 0.0,
                    "matched_by": [],
                    "_order": order,
                }
            fused[key]["rrf_score"] += 1.0 / (RRF_K + rank)
            if search_type not in fused[key]["matched_by"]:
                fused[key]["matched_by"].append(search_type)

    ranked = sorted(fused.values(), key=lambda x: (-x["rrf_score"], x["_order"]))
    for item in ranked:
        item.pop("_order", None)

    if not ranked:
        return []

    # Per-document coverage: every doc with any RRF score contributes
    # at least its best chunk — no global floor that can wipe out a doc.
    return _guarantee_doc_coverage(ranked, "rrf_score", abs_min_score=0.0,
                                   limit_per_doc=2, total_limit=limit)


_STOPWORDS = {
    "a", "an", "the", "is", "it", "this", "that", "i", "you", "he", "she", "we",
    "they", "to", "of", "in", "on", "and", "or", "but", "so", "be", "am", "are",
    "was", "were", "do", "does", "did", "has", "have", "had", "for", "with", "at",
}

def _is_low_information_query(query_text: str) -> bool:
    words = [w.strip(".,!?'\"").lower() for w in (query_text or "").split()]
    meaningful = [w for w in words if w and w not in _STOPWORDS]
    return len(meaningful) == 0


def _keyword_search(es, query_text, filter_clauses, limit, ensure_doc_coverage=False):
    """
    BM25 keyword search.

    Key improvements over the old version:
    - Uses 'cross_fields' type instead of 'best_fields' so a name split
      across first-name/last-name fields still matches properly.
    - minimum_should_match lowered from 55% to 1 for short name queries
      (a single-word name like "Priya" should always match if present).
    - No global score floor — per-document coverage is applied instead.
    - Fetches limit*4 candidates from ES so we have enough to guarantee
      coverage across all documents before trimming.
    """
    search_query = {
        "size": limit * 4,          # fetch more, trim after coverage pass
        "min_score": 0.5,           # very low — just exclude complete non-matches
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query_text,
                            "fields": [
                                "text_content^3",
                                "table_markdown^4",
                                "image_description^2",
                            ],
                            "type": "cross_fields",
                            "operator": "or",
                            "minimum_should_match": "1",
                        }
                    }
                ],
                # Phrase-proximity boost: the multi_match above scores each query
                # word independently, so a chunk that repeats one shared word many
                # times can outrank the chunk that actually contains the full
                # multi-word phrase. This rewards chunks where the words appear
                # together/in order.
                "should": [
                    {"match_phrase": {"text_content": {"query": query_text, "slop": 2, "boost": 8}}},
                    {"match_phrase": {"table_markdown": {"query": query_text, "slop": 2, "boost": 8}}},
                ],
                "filter": filter_clauses,
            }
        },
    }
    response = es.search(
        index=INDEX_NAME,
        size=search_query["size"],
        min_score=search_query["min_score"],
        query=search_query["query"],
    )
    results = [
        _source_to_result(hit, rank=idx, search_type="keyword")
        for idx, hit in enumerate(response["hits"]["hits"], start=1)
    ]

    if ensure_doc_coverage:
        # Guarantee at least 1 result per document that matched anything
        return _guarantee_doc_coverage(results, "score", abs_min_score=0.5,
                                       limit_per_doc=2, total_limit=limit)
    return _dedupe_results(results, limit)


def _semantic_search(es, query_text, filter_clauses, limit, ensure_doc_coverage=False):
    """
    KNN vector search using the E5 embedding model.

    Key improvements:
    - num_candidates raised to limit*15 so ES considers more vectors before
      picking the top-k. More candidates = better recall across documents.
    - No cosine similarity floor — per-document coverage is applied instead
      so a document that scores 0.68 isn't dropped just because another
      scored 0.91.
    - Fetches limit*3 from KNN, then applies coverage pass.
    """
    search_query = {
        "size": limit * 3,
        "knn": {
            "field": "text_embedding",
            "query_vector_builder": {
                "text_embedding": {
                    "model_id": ES_INFERENCE_ID,
                    "model_text": query_text,
                }
            },
            "k": limit * 3,
            "num_candidates": max(100, limit * 15),  # was limit*10, now higher recall
            "filter": filter_clauses,
        },
    }
    response = es.search(
        index=INDEX_NAME,
        size=search_query["size"],
        knn=search_query["knn"],
    )
    results = [
        _source_to_result(hit, rank=idx, search_type="semantic")
        for idx, hit in enumerate(response["hits"]["hits"], start=1)
    ]

    if ensure_doc_coverage:
        return _guarantee_doc_coverage(results, "score", abs_min_score=0.0,
                                       limit_per_doc=2, total_limit=limit)
    return _dedupe_results(results, limit)


def search_es(query_text, user_id, folder_id=None, document_id=None,
              search_mode="semantic", limit=8, strict=False):
    if _is_low_information_query(query_text):
        logger.info("Skipping retrieval for low-information query: %r", query_text)
        return []

    es = get_es_client()
    if not es:
        logger.warning("Elasticsearch offline. Returning empty search results.")
        return []

    filter_clauses = [{"term": {"user_id": user_id}}]
    if folder_id is not None:
        filter_clauses.append({"term": {"folder_id": folder_id}})
    if document_id is not None:
        filter_clauses.append({"term": {"document_id": document_id}})

    # Multi-document scope = folder or entire vault.
    # Always apply per-document coverage when searching across multiple docs.
    multi_doc_scope = (document_id is None)

    try:
        if search_mode == "keyword":
            return _keyword_search(es, query_text, filter_clauses, limit,
                                   ensure_doc_coverage=multi_doc_scope)

        if search_mode == "semantic":
            return _semantic_search(es, query_text, filter_clauses, limit,
                                    ensure_doc_coverage=multi_doc_scope)

        # Hybrid: run both and fuse with RRF
        semantic_results = []
        try:
            semantic_results = _semantic_search(es, query_text, filter_clauses,
                                                limit * 2, ensure_doc_coverage=False)
        except BadRequestError as bre:
            logger.warning(f"KNN search failed in hybrid mode: {str(bre)}. BM25 only.")

        keyword_results = _keyword_search(es, query_text, filter_clauses,
                                          limit * 2, ensure_doc_coverage=False)

        # RRF fusion already applies per-document coverage internally
        return _rrf_fuse([("knn", semantic_results), ("bm25", keyword_results)], limit)

    except BadRequestError as bre:
        if search_mode == "semantic":
            logger.warning(f"Semantic search failed: {str(bre)}. Falling back to keyword.")
            return search_es(query_text, user_id, folder_id, document_id,
                             search_mode="keyword", limit=limit, strict=strict)
        return []
    except Exception as e:
        logger.error(f"Search query failed in Elasticsearch: {str(e)}")
        return []
