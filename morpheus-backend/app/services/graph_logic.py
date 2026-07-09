from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.database import supabase

_embedder = SentenceTransformer("all-MiniLM-L6-v2")


def normalize_keyword_name(name: Optional[str]) -> str:
    """Return the shared graph node ID for a keyword/symbol name."""
    if not name:
        return ""
    return name.strip().lower()


def build_graph_data(user_id: str) -> dict:
    """Build dream-keyword graph data for frontend visualization."""
    dreams_response = (
        supabase.table("dreams")
        .select("id,title,created_at")
        .eq("user_id", user_id)
        .execute()
    )
    dreams = dreams_response.data or []
    dream_ids = [dream["id"] for dream in dreams if dream.get("id")]

    if not dream_ids:
        return {"nodes": [], "links": []}

    links_response = (
        supabase.table("dream_keywords")
        .select("dream_id,keyword_id")
        .in_("dream_id", dream_ids)
        .execute()
    )
    dream_keywords = links_response.data or []

    # Count distinct dreams per keyword (keyed by DB keyword UUID).
    _kw_dream_sets: dict[str, set] = {}
    for row in dream_keywords:
        kid = row.get("keyword_id")
        did = row.get("dream_id")
        if kid and did:
            _kw_dream_sets.setdefault(kid, set()).add(did)
    kw_dream_count_by_db_id: dict[str, int] = {k: len(v) for k, v in _kw_dream_sets.items()}

    keyword_ids = sorted(
        {
            row["keyword_id"]
            for row in dream_keywords
            if row.get("keyword_id")
        }
    )

    keywords = []
    if keyword_ids:
        keywords_response = (
            supabase.table("keywords")
            .select("id,name")
            .in_("id", keyword_ids)
            .execute()
        )
        keywords = keywords_response.data or []

    nodes = []
    for dream in dreams:
        dream_id = dream.get("id")
        if not dream_id:
            continue
        nodes.append(
            {
                "id": f"dream-{dream_id}",
                "label": dream.get("title") or "Untitled Dream",
                "type": "dream",
                "color": "#FFDE6E",
                "created_at": dream.get("created_at"),
            }
        )

    keyword_node_ids_by_row_id = {}
    keyword_node_ids = set()
    keyword_node_names = []
    for keyword in keywords:
        keyword_id = keyword.get("id")
        keyword_node_id = normalize_keyword_name(keyword.get("name"))
        if not keyword_id or not keyword_node_id:
            continue
        keyword_node_ids_by_row_id[keyword_id] = keyword_node_id

        if keyword_node_id in keyword_node_ids:
            continue

        keyword_node_ids.add(keyword_node_id)
        keyword_node_names.append(keyword_node_id)
        nodes.append(
            {
                "id": keyword_node_id,
                "label": keyword_node_id,
                "type": "keyword",
                "color": "#8A7129",
                "dream_count": kw_dream_count_by_db_id.get(keyword_id, 0),
            }
        )

    links = []
    link_keys = set()
    dream_id_set = set(dream_ids)
    for row in dream_keywords:
        dream_id = row.get("dream_id")
        keyword_id = row.get("keyword_id")
        if not dream_id or not keyword_id:
            continue
        keyword_node_id = keyword_node_ids_by_row_id.get(keyword_id)
        if dream_id not in dream_id_set or not keyword_node_id:
            continue

        source = f"dream-{dream_id}"
        target = keyword_node_id
        link_key = (source, target)
        if link_key in link_keys:
            continue
        link_keys.add(link_key)

        links.append(
            {
                "source": source,
                "target": target,
                "type": "dream_keyword",
            }
        )

    if len(keyword_node_names) >= 2:
        embeddings = _embedder.encode(keyword_node_names)
        similarity_matrix = cosine_similarity(embeddings)

        for source_index, source_keyword in enumerate(keyword_node_names):
            for target_index in range(source_index + 1, len(keyword_node_names)):
                target_keyword = keyword_node_names[target_index]
                if source_keyword == target_keyword:
                    continue
                if similarity_matrix[source_index][target_index] < 0.65:
                    continue

                links.append(
                    {
                        "source": source_keyword,
                        "target": target_keyword,
                        "type": "similar",
                    }
                )

    # -----------------------------------------------------------------------
    # Cluster-aware dream count & dominant node detection
    # -----------------------------------------------------------------------
    # Build adjacency from the similar links just created.
    adj: dict[str, set] = defaultdict(set)
    for link in links:
        if link["type"] == "similar":
            adj[link["source"]].add(link["target"])
            adj[link["target"]].add(link["source"])

    # Map keyword_node_id → set of dream_ids it is directly linked to.
    node_dream_ids: dict[str, set] = {}
    for row in dream_keywords:
        did = row.get("dream_id")
        kid = row.get("keyword_id")
        if not did or not kid:
            continue
        node_id = keyword_node_ids_by_row_id.get(kid)
        if not node_id:
            continue
        node_dream_ids.setdefault(node_id, set()).add(did)

    # BFS over similarity adjacency to compute pooled dream count per cluster.
    visited: set[str] = set()
    cluster_dream_count: dict[str, int] = {}
    for start in keyword_node_names:
        if start in visited:
            continue
        cluster: list[str] = []
        queue = [start]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            cluster.append(current)
            queue.extend(adj[current] - visited)
        combined: set = set()
        for member in cluster:
            combined |= node_dream_ids.get(member, set())
        count = len(combined)
        for member in cluster:
            cluster_dream_count[member] = count

    # Determine account age from the earliest dream timestamp.
    earliest: Optional[datetime] = None
    for dream in dreams:
        created = dream.get("created_at")
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if earliest is None or dt < earliest:
                earliest = dt
        except ValueError:
            pass

    account_age_days = 0
    if earliest:
        account_age_days = (datetime.now(timezone.utc) - earliest).days

    max_cluster_count = max(cluster_dream_count.values(), default=0)

    # Patch cluster_dream_count and is_dominant onto every keyword node.
    for node in nodes:
        if node.get("type") != "keyword":
            continue
        cdc = cluster_dream_count.get(node["id"], node.get("dream_count", 0))
        node["cluster_dream_count"] = cdc
        node["is_dominant"] = bool(
            account_age_days >= 90
            and max_cluster_count > 0
            and cdc == max_cluster_count
        )

    return {
        "nodes": nodes,
        "links": links,
    }
