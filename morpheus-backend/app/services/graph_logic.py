import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.crypto import decrypt_dream_row
from supabase import Client


EMOTION_COLORS: dict[str, str] = {
    "fear":        "#C0392B",
    "anxiety":     "#8E44AD",
    "sadness":     "#5B8FA8",
    "grief":       "#4A6FA5",
    "anger":       "#E74C3C",
    "joy":         "#F4D03F",
    "love":        "#E8A0BF",
    "peace":       "#A8D8A8",
    "connection":  "#1ABC9C",
    "longing":     "#E67E22",
    "confusion":   "#7F8C8D",
    "wonder":      "#D4AC0D",
    "shame":       "#A04000",
    "guilt":       "#784212",
    "excitement":  "#F39C12",
    "uncertainty": "#95A5A6",
}
DEFAULT_DREAM_COLOR = "#FFDE6E"
KEYWORD_STOPWORDS = {
    "a",
    "an",
    "and",
    "of",
    "the",
    "with",
}
KEYWORD_PREPOSITIONS = {"at", "in", "into", "of", "on", "to", "with"}


def _core_keyword_phrase(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", name.lower())
    for index, word in enumerate(words):
        if word in KEYWORD_PREPOSITIONS:
            return " ".join(words[:index])
    return " ".join(words)


def _keyword_tokens(name: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", _core_keyword_phrase(name)):
        if token in KEYWORD_STOPWORDS:
            continue
        if len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        tokens.add(token)
    return tokens


def _has_meaningful_keyword_overlap(left: str, right: str) -> bool:
    left_tokens = _keyword_tokens(left)
    right_tokens = _keyword_tokens(right)
    for left_token in left_tokens:
        for right_token in right_tokens:
            if left_token == right_token:
                return True
            if len(left_token) >= 3 and right_token.startswith(left_token):
                return True
            if len(right_token) >= 3 and left_token.startswith(right_token):
                return True
    return False


def _emotion_color(emotions: list) -> str:
    for e in emotions:
        key = e.strip().lower()
        if key in EMOTION_COLORS:
            return EMOTION_COLORS[key]
    return DEFAULT_DREAM_COLOR


def normalize_keyword_name(name: Optional[str]) -> str:
    if not name:
        return ""
    return name.strip().lower()


def _vector_cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(x * y for x, y in zip(left, right))
    norm_left = math.sqrt(sum(x * x for x in left))
    norm_right = math.sqrt(sum(x * x for x in right))
    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


def build_graph_data(db: Client, user_id: str) -> dict:
    """Build dream graph data supporting both keyword and emotion clustering."""
    dreams_response = (
        db.table("dreams")
        .select("id,title,created_at,emotions")
        .execute()
    )
    # Titles are stored encrypted; decrypt so graph labels/tooltips show real text.
    dreams = [decrypt_dream_row(d) for d in (dreams_response.data or [])]
    dream_ids = [d["id"] for d in dreams if d.get("id")]

    if not dream_ids:
        return {
            "nodes": [],
            "keyword_links": [],
            "emotion_links": [],
            "emotion_colors": EMOTION_COLORS,
        }

    links_response = (
        db.table("dream_keywords")
        .select("dream_id,keyword_id")
        .in_("dream_id", dream_ids)
        .execute()
    )
    dream_keywords = links_response.data or []

    # --- keyword node counts ---
    _kw_dream_sets: dict[str, set] = {}
    for row in dream_keywords:
        kid, did = row.get("keyword_id"), row.get("dream_id")
        if kid and did:
            _kw_dream_sets.setdefault(kid, set()).add(did)
    kw_dream_count_by_db_id = {k: len(v) for k, v in _kw_dream_sets.items()}

    keyword_ids = sorted({r["keyword_id"] for r in dream_keywords if r.get("keyword_id")})
    keywords = []
    if keyword_ids:
        keywords = (
            db.table("keywords")
            .select("id,name")
            .in_("id", keyword_ids)
            .execute()
        ).data or []

    # --- dream nodes (colored by dominant emotion) ---
    nodes = []
    dream_emotions: dict[str, list] = {}
    for dream in dreams:
        dream_id = dream.get("id")
        if not dream_id:
            continue
        emotions = dream.get("emotions") or []
        dream_emotions[dream_id] = emotions
        dominant = emotions[0].strip().lower() if emotions else None
        nodes.append({
            "id": f"dream-{dream_id}",
            "label": dream.get("title") or "Untitled Dream",
            "type": "dream",
            "color": _emotion_color(emotions),
            "dominant_emotion": dominant,
            "created_at": dream.get("created_at"),
        })

    # --- keyword nodes ---
    keyword_node_ids_by_row_id: dict[str, str] = {}
    keyword_node_ids: set[str] = set()
    keyword_node_names: list[str] = []
    for keyword in keywords:
        kid = keyword.get("id")
        knode_id = normalize_keyword_name(keyword.get("name"))
        if not kid or not knode_id:
            continue
        keyword_node_ids_by_row_id[kid] = knode_id
        if knode_id in keyword_node_ids:
            continue
        keyword_node_ids.add(knode_id)
        keyword_node_names.append(knode_id)
        nodes.append({
            "id": knode_id,
            "label": knode_id,
            "type": "keyword",
            "color": "#8A7129",
            "dream_count": kw_dream_count_by_db_id.get(kid, 0),
        })

    # --- emotion nodes ---
    seen_emotions: set[str] = set()
    for ems in dream_emotions.values():
        for e in ems:
            key = e.strip().lower()
            if key and key not in seen_emotions:
                seen_emotions.add(key)
                nodes.append({
                    "id": f"emotion-{key}",
                    "label": key,
                    "type": "emotion",
                    "color": EMOTION_COLORS.get(key, "#95A5A6"),
                })

    # --- keyword links ---
    keyword_links = []
    link_keys: set = set()
    dream_id_set = set(dream_ids)
    for row in dream_keywords:
        did = row.get("dream_id")
        kid = row.get("keyword_id")
        if not did or not kid:
            continue
        knode_id = keyword_node_ids_by_row_id.get(kid)
        if did not in dream_id_set or not knode_id:
            continue
        lk = (f"dream-{did}", knode_id)
        if lk in link_keys:
            continue
        link_keys.add(lk)
        keyword_links.append({"source": f"dream-{did}", "target": knode_id, "type": "dream_keyword"})

    if len(keyword_node_names) >= 2:
        # MiniLM everywhere (local and Render), one batched pass, no API calls.
        from app.services.embeddings import embed_texts

        embs = embed_texts(keyword_node_names)
        for i, src in enumerate(keyword_node_names):
            for j in range(i + 1, len(keyword_node_names)):
                dst = keyword_node_names[j]
                if src == dst:
                    continue
                if _vector_cosine_similarity(embs[i], embs[j]) < settings.GRAPH_LOCAL_SIMILARITY_THRESHOLD:
                    continue
                keyword_links.append({"source": src, "target": dst, "type": "similar"})

    # --- emotion links ---
    emotion_links = []
    emotion_link_keys: set = set()
    for did, ems in dream_emotions.items():
        for e in ems:
            key = e.strip().lower()
            if not key:
                continue
            src = f"dream-{did}"
            tgt = f"emotion-{key}"
            lk = (src, tgt)
            if lk in emotion_link_keys:
                continue
            emotion_link_keys.add(lk)
            emotion_links.append({"source": src, "target": tgt, "type": "dream_emotion"})

    # --- cluster / dominant detection (keyword mode) ---
    adj: dict[str, set] = defaultdict(set)
    for link in keyword_links:
        if link["type"] == "similar":
            adj[link["source"]].add(link["target"])
            adj[link["target"]].add(link["source"])

    node_dream_ids: dict[str, set] = {}
    for row in dream_keywords:
        did = row.get("dream_id")
        kid = row.get("keyword_id")
        if not did or not kid:
            continue
        nid = keyword_node_ids_by_row_id.get(kid)
        if not nid:
            continue
        node_dream_ids.setdefault(nid, set()).add(did)

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
    account_age_days = (datetime.now(timezone.utc) - earliest).days if earliest else 0
    max_cluster_count = max(cluster_dream_count.values(), default=0)

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
        "keyword_links": keyword_links,
        "emotion_links": emotion_links,
        "emotion_colors": EMOTION_COLORS,
    }
