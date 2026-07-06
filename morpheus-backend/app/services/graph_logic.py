from typing import Optional

from app.database import supabase


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
    for keyword in keywords:
        keyword_id = keyword.get("id")
        keyword_node_id = normalize_keyword_name(keyword.get("name"))
        if not keyword_id or not keyword_node_id:
            continue
        keyword_node_ids_by_row_id[keyword_id] = keyword_node_id

        if keyword_node_id in keyword_node_ids:
            continue

        keyword_node_ids.add(keyword_node_id)
        nodes.append(
            {
                "id": keyword_node_id,
                "label": keyword_node_id,
                "type": "keyword",
                "color": "#8A7129",
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
            }
        )

    return {
        "nodes": nodes,
        "links": links,
    }
