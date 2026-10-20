import re
import sqlite3

from .db import connect, now, transaction


class InputError(ValueError):
    pass


def normalize_title(title):
    return title.strip().lower()


def validate_point(title, nodes):
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 255:
        raise InputError("Point 标题不能为空且不能超过 255 字符")
    if not isinstance(nodes, list) or not nodes:
        raise InputError("请至少添加一条释义或说明")
    def check(items, depth=0):
        if depth > 12 or len(items) > 200:
            raise InputError("内容层级或节点数量过多")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("content"), str) or not item["content"].strip():
                raise InputError("释义内容不能为空")
            if len(item["content"]) > 2000:
                raise InputError("单条释义不能超过 2000 字符")
            children = item.get("children", [])
            if not isinstance(children, list):
                raise InputError("子级内容格式错误")
            check(children, depth + 1)
    check(nodes)


def _save_nodes(db, point_id, nodes, parent_id=None):
    stamp = now()
    for order, node in enumerate(nodes):
        cursor = db.execute(
            "INSERT INTO point_content_nodes(point_id,parent_id,content,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (point_id, parent_id, node["content"].strip(), order, stamp, stamp),
        )
        _save_nodes(db, point_id, node.get("children", []), cursor.lastrowid)


def _create(db, title, nodes, source_type):
    validate_point(title, nodes)
    stamp = now()
    cursor = db.execute(
        "INSERT INTO points(user_id,title,normalized_title,source_type,created_at,updated_at) VALUES(1,?,?,?,?,?)",
        (title.strip(), normalize_title(title), source_type, stamp, stamp),
    )
    point_id = cursor.lastrowid
    _save_nodes(db, point_id, nodes)
    db.execute("INSERT INTO point_review_states(point_id,updated_at) VALUES(?,?)", (point_id, stamp))
    return point_id


def create_point(title, nodes, source_type="MANUAL"):
    try:
        with transaction(immediate=True) as db:
            point_id = _create(db, title, nodes, source_type)
        return get_point(point_id)
    except sqlite3.IntegrityError as exc:
        raise InputError("同名 Point 已存在") from exc


def _tree(rows):
    items = {row["id"]: {"id": row["id"], "content": row["content"], "children": []} for row in rows}
    roots = []
    for row in rows:
        item = items[row["id"]]
        parent = items.get(row["parent_id"])
        (parent["children"] if parent else roots).append(item)
    return roots


def get_point(point_id):
    with connect() as db:
        row = db.execute("""SELECT p.*,s.mastery,s.last_reviewed_at,s.next_review_at,
            s.review_count,s.correct_count,s.wrong_count,s.correct_streak
            FROM points p JOIN point_review_states s ON s.point_id=p.id
            WHERE p.id=? AND p.user_id=1 AND p.deleted_at IS NULL""", (point_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        rows = db.execute("SELECT * FROM point_content_nodes WHERE point_id=? ORDER BY id", (point_id,)).fetchall()
        result["nodes"] = _tree(rows)
        return result


def list_points(query=""):
    with connect() as db:
        return [dict(row) for row in db.execute("""SELECT p.id,p.title,p.source_type,p.created_at,
            s.mastery,s.last_reviewed_at,s.next_review_at,s.review_count
            FROM points p JOIN point_review_states s ON s.point_id=p.id
            WHERE p.user_id=1 AND p.deleted_at IS NULL AND p.title LIKE ? ESCAPE '\\'
            ORDER BY p.created_at DESC,p.id DESC""", ("%" + re.sub(r"([%_\\])", r"\\\1", query.strip()) + "%",))]


def update_point(point_id, title, nodes):
    validate_point(title, nodes)
    try:
        with transaction(immediate=True) as db:
            found = db.execute("SELECT id FROM points WHERE id=? AND user_id=1 AND deleted_at IS NULL", (point_id,)).fetchone()
            if not found:
                return None
            db.execute("UPDATE points SET title=?,normalized_title=?,updated_at=? WHERE id=?",
                       (title.strip(), normalize_title(title), now(), point_id))
            # Historical questions keep their text. Their target node becomes NULL if it was removed.
            db.execute("DELETE FROM point_content_nodes WHERE point_id=?", (point_id,))
            _save_nodes(db, point_id, nodes)
        return get_point(point_id)
    except sqlite3.IntegrityError as exc:
        raise InputError("同名 Point 已存在") from exc


def delete_point(point_id):
    with transaction(immediate=True) as db:
        changed = db.execute("UPDATE points SET deleted_at=?,updated_at=? WHERE id=? AND user_id=1 AND deleted_at IS NULL",
                             (now(), now(), point_id)).rowcount
    return bool(changed)


def _parse_markdown(markdown):
    if not isinstance(markdown, str) or len(markdown) > 200_000:
        raise InputError("Markdown 内容无效或过长")
    points = []
    stack = []
    for number, raw in enumerate(markdown.splitlines(), 1):
        if not raw.strip():
            continue
        match = re.match(r"^(\s*)[-*+]\s+(.+?)\s*$", raw)
        if not match:
            raise InputError(f"第 {number} 行不是无序列表项")
        indent = len(match.group(1).expandtabs(2))
        content = match.group(2).strip()
        if not content:
            raise InputError(f"第 {number} 行内容为空")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            if indent != 0:
                raise InputError(f"第 {number} 行顶层 Point 应从行首开始")
            current = {"title": content, "nodes": [], "line": number}
            points.append(current)
            stack.append((indent, current["nodes"]))
        else:
            node = {"content": content, "children": []}
            stack[-1][1].append(node)
            stack.append((indent, node["children"]))
    if not points:
        raise InputError("请粘贴至少一个 Point")
    for point in points:
        validate_point(point["title"], point["nodes"])
    return points


def preview_markdown(markdown):
    parsed = _parse_markdown(markdown)
    with connect() as db:
        existing = {row[0] for row in db.execute("SELECT normalized_title FROM points WHERE user_id=1 AND deleted_at IS NULL")}
    seen = set()
    for point in parsed:
        key = normalize_title(point["title"])
        point["duplicate"] = key in existing or key in seen
        seen.add(key)
    return parsed


def import_markdown(markdown):
    parsed = _parse_markdown(markdown)
    created = []
    skipped = []
    with transaction(immediate=True) as db:
        existing = {row[0] for row in db.execute("SELECT normalized_title FROM points WHERE user_id=1 AND deleted_at IS NULL")}
        for point in parsed:
            key = normalize_title(point["title"])
            if key in existing:
                skipped.append(point["title"])
                continue
            created.append(_create(db, point["title"], point["nodes"], "MARKDOWN"))
            existing.add(key)
    return {"createdIds": created, "skippedTitles": skipped}
