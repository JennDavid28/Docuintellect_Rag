import os
import re
import json
import logging
from collections import defaultdict

from groq import Groq
import networkx as nx

logger = logging.getLogger(__name__)

def get_groq_client():
    return Groq(api_key=os.environ["GROQ_API_KEY"].strip(), timeout=30.0)

def extract_triples_local(text_content: str, max_triples: int = 15) -> list:
    text_content = re.sub(r'\s+', ' ', text_content)
    sentences = re.split(r'[.!?]', text_content)
    triples = []
    verbs = ["regulates", "contains", "develops", "implements", "controls",
             "causes", "affects", "manages", "defines", "limits", "applies to",
             "is part of", "associated with", "requires", "sends", "receives"]
    verb_pattern = r'\b(' + '|'.join(verbs) + r')\b'

    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 15 or len(sent) > 200:
            continue
        match = re.search(verb_pattern, sent, re.IGNORECASE)
        if match:
            verb = match.group(1)
            parts = sent.split(match.group(0), 1)
            if len(parts) == 2:
                subj = re.sub(r'^[^\w]+|[^\w]+$', '', parts[0]).strip()
                obj = re.sub(r'^[^\w]+|[^\w]+$', '', parts[1]).strip()
                subj = " ".join(subj.split()[-3:])
                obj = " ".join(obj.split()[:3])
                if subj and obj and len(subj) > 2 and len(obj) > 2:
                    triples.append({
                        "source": subj.title(),
                        "relationship": verb.lower(),
                        "target": obj.title()
                    })
                    if len(triples) >= max_triples:
                        break

    if not triples:
        candidates = re.findall(r"\b[A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,3}\b", text_content)
        stop_terms = {"The", "This", "That", "These", "Those", "Page", "Figure", "Table", "Document"}
        counts = {}
        for item in candidates:
            item = item.strip()
            if len(item) < 3 or item in stop_terms:
                continue
            counts[item] = counts.get(item, 0) + 1
        top_entities = [name for name, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]]
        for idx in range(len(top_entities) - 1):
            triples.append({
                "source": top_entities[idx],
                "relationship": "appears with",
                "target": top_entities[idx + 1]
            })
            if len(triples) >= max_triples:
                break

    if not triples:
        triples = [{"source": "Document", "relationship": "contains", "target": "Extracted Text"}]
    return triples

def extract_triples_gemini(text_content: str) -> list:
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key or len(groq_key) < 20:
        return extract_triples_local(text_content)

    model = os.environ.get("GROQ_TEXT_MODEL", "llama-3.1-8b-instant")

    try:
        client = get_groq_client()
        prompt = f"""Analyze the text below and extract the key entities and their relationships.
Return the output ONLY as a valid JSON array of objects, where each object has "source", "relationship", and "target" fields.
Keep the list focused on the 10-15 most critical relationships.
Do not include any markdown wrappers or text outside the JSON array.

Text:
{text_content[:4000]}"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0,   # was unset (defaults to randomness) — pin to 0 for repeatable extraction
            seed=42,        # Groq supports a seed param for reproducibility on supported model
        )
        response_text = response.choices[0].message.content.strip()

        if response_text.startswith("```"):
            response_text = re.sub(r'^```(?:json)?\n', '', response_text)
            response_text = re.sub(r'\n```$', '', response_text)

        triples = json.loads(response_text)
        if isinstance(triples, list):
            return triples
        return extract_triples_local(text_content)
    except Exception as e:
        logger.error(f"Groq Knowledge Graph extraction failed: {str(e)}")
        return extract_triples_local(text_content)

_PALETTE = [
    "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
]

def _build_communities(g_undirected, min_community_size=2):
    """Topic clustering. greedy_modularity_communities on a small/sparse
    graph (10-20 nodes) tends to fragment into many singleton/pair
    communities — visually that means most nodes get flung into their own
    isolated corner instead of grouping meaningfully. Merge any community
    smaller than min_community_size into whichever larger community it has
    the most edges to (or the single largest community as a fallback)."""
    if g_undirected.number_of_nodes() == 0:
        return {}
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        if g_undirected.number_of_edges() == 0:
            communities = [set(g_undirected.nodes())]
        else:
            communities = list(greedy_modularity_communities(g_undirected, resolution=0.6))
    except Exception as exc:
        logger.warning("Community detection failed, defaulting to one cluster: %s", exc)
        communities = [set(g_undirected.nodes())]

    communities = [set(c) for c in communities]
    big = [c for c in communities if len(c) >= min_community_size]
    small = [c for c in communities if len(c) < min_community_size]

    if not big:
        big = [set(g_undirected.nodes())]
        small = []

    for small_comm in small:
        for node in small_comm:
            neighbors = set(g_undirected.neighbors(node))
            best_idx, best_overlap = 0, -1
            for idx, comm in enumerate(big):
                overlap = len(neighbors & comm)
                if overlap > best_overlap:
                    best_idx, best_overlap = idx, overlap
            big[best_idx].add(node)

    node_to_community = {}
    for idx, community in enumerate(big):
        for node in community:
            node_to_community[node] = idx
    return node_to_community


def _layout_with_clusters(g, node_to_community, seed=42):
    """Seed each cluster around its own point on a circle, then run spring
    layout from there. Radius scales with sqrt(node count) instead of
    linearly with cluster count, and k is raised so connected nodes don't
    collapse onto the exact same point — that's what was causing labels
    like 'OpenAI/ChatGPT' and 'Developers/GitHub' to overlap completely."""
    import math, random
    n_communities = max(node_to_community.values(), default=0) + 1
    n_nodes = max(g.number_of_nodes(), 1)
    radius = 1.4 + 0.55 * math.sqrt(n_nodes)
    centers = {
        cid: (radius * math.cos(2 * math.pi * cid / max(n_communities, 1)),
              radius * math.sin(2 * math.pi * cid / max(n_communities, 1)))
        for cid in range(n_communities)
    }

    rng = random.Random(seed)
    initial_pos = {}
    for node in g.nodes():
        cx, cy = centers.get(node_to_community.get(node, 0), (0, 0))
        initial_pos[node] = (cx + rng.uniform(-0.6, 0.6), cy + rng.uniform(-0.6, 0.6))

    try:
        pos = nx.spring_layout(g, pos=initial_pos, k=1.4, iterations=150, seed=seed)
    except Exception:
        pos = initial_pos
    return pos


def build_knowledge_graph_data(triples: list) -> dict:
    """Build a richly-annotated graph payload: cluster-by-topic, degree +
    centrality based node sizing (so the most-connected entities pop out),
    and summary analytics — for the frontend to render directly as SVG."""
    g = nx.DiGraph()
    for t in triples:
        source = (t.get("source") or "").strip()
        target = (t.get("target") or "").strip()
        relationship = (t.get("relationship") or "related to").strip()
        if not source or not target:
            continue
        g.add_edge(source, target, relationship=relationship)

    if g.number_of_nodes() == 0:
        return {"nodes": [], "edges": [], "communities": [],
                "stats": {"entities": 0, "relationships": 0, "clusters": 0, "density": 0.0}}

    g_undirected = g.to_undirected()
    node_to_community = _build_communities(g_undirected)
    pos = _layout_with_clusters(g, node_to_community)

    degree = dict(g_undirected.degree())
    try:
        centrality = nx.degree_centrality(g_undirected)
    except Exception:
        centrality = {n: 0.0 for n in g.nodes()}

    max_degree = max(degree.values()) if degree else 1

    nodes = []
    for node in g.nodes():
        cid = node_to_community.get(node, 0)
        deg = degree.get(node, 0)
        nodes.append({
            "id": node,
            "label": node,
            "community": cid,
            "color": _PALETTE[cid % len(_PALETTE)],
            "degree": deg,
            "centrality": round(centrality.get(node, 0.0), 3),
            "size": round(10 + 16 * (deg / max_degree), 1) if max_degree else 14,
            "x": round(pos[node][0], 4),
            "y": round(pos[node][1], 4),
        })

    edges = [
        {"source": u, "target": v, "relationship": data.get("relationship", "related to")}
        for u, v, data in g.edges(data=True)
    ]

    community_counts = defaultdict(int)
    for n in nodes:
        community_counts[n["community"]] += 1
    communities = [
        {"id": cid, "label": f"Cluster {cid + 1}", "color": _PALETTE[cid % len(_PALETTE)], "size": count}
        for cid, count in sorted(community_counts.items())
    ]

    top_central = sorted(nodes, key=lambda n: n["centrality"], reverse=True)[:5]

    stats = {
        "entities": g.number_of_nodes(),
        "relationships": g.number_of_edges(),
        "clusters": len(communities),
        "density": round(nx.density(g), 3),
        "top_entities": [
            {"label": n["label"], "centrality": n["centrality"], "degree": n["degree"]}
            for n in top_central
        ],
    }

    return {"nodes": nodes, "edges": edges, "communities": communities, "stats": stats}