import json
from datetime import datetime, timedelta, timezone

from .ai import GenerationError, configured, generate_question
from .db import connect, now, transaction
from .points import InputError, get_point


def _candidate_rows(db):
    return db.execute("""SELECT p.id,p.title,s.mastery,s.next_review_at,s.last_reviewed_at,
        (SELECT a.is_correct FROM review_attempts a WHERE a.point_id=p.id ORDER BY a.answered_at DESC,a.id DESC LIMIT 1) AS last_correct
        FROM points p JOIN point_review_states s ON s.point_id=p.id
        WHERE p.user_id=1 AND p.deleted_at IS NULL""").fetchall()


def _rank(row, stamp):
    next_at = datetime.fromisoformat(row["next_review_at"]) if row["next_review_at"] else None
    due = next_at is None or next_at <= stamp
    overdue_days = max(0, (stamp - next_at).days) if next_at else 0
    mastery = row["mastery"]
    score = min(overdue_days, 10) * 3 + (0 if mastery is None else (5 - mastery) * 8)
    score += 15 if row["last_correct"] == 0 else 0
    score += 20 if mastery is None else 0
    # Due Points first. Fill with weak Points, then oldest reviewed Points.
    last = row["last_reviewed_at"] or ""
    return (0 if due else 1, -score, mastery if mastery is not None else 0, last, row["id"])


def candidates():
    with connect() as db:
        rows = _candidate_rows(db)
    stamp = datetime.now(timezone.utc)
    return [dict(row) for row in sorted(rows, key=lambda row: _rank(row, stamp))]


def review_preview():
    rows = candidates()
    stamp = datetime.now(timezone.utc)
    due = sum(1 for row in rows if row["next_review_at"] is None or datetime.fromisoformat(row["next_review_at"]) <= stamp)
    return {"availableCount": len(rows), "dueCount": due, "plannedCount": min(10, len(rows)),
            "points": [{"id": row["id"], "title": row["title"]} for row in rows[:10]],
            "aiConfigured": configured()}


def create_session():
    if not configured():
        raise InputError("AI 尚未配置。请按 README 设置 OPENAI_API_KEY 和 OPENAI_MODEL")
    rows = candidates()
    if not rows:
        raise InputError("还没有可复习的 Point，请先添加")
    planned = min(10, len(rows))
    with transaction(immediate=True) as db:
        cursor = db.execute("INSERT INTO review_sessions(user_id,status,planned_question_count,created_at) VALUES(1,'GENERATING',?,?)",
                            (planned, now()))
        session_id = cursor.lastrowid
    questions = []
    errors = []
    for row in rows:
        if len(questions) >= planned:
            break
        point = get_point(row["id"])
        if not point:
            continue
        for _ in range(2):
            try:
                questions.append(generate_question(point))
                break
            except GenerationError as exc:
                errors.append(str(exc))
    with transaction(immediate=True) as db:
        if not questions:
            db.execute("UPDATE review_sessions SET status='FAILED' WHERE id=?", (session_id,))
            raise_after = True
        else:
            for order, item in enumerate(questions):
                db.execute("""INSERT INTO review_questions(session_id,point_id,target_node_id,question_type,
                    context_text,prompt_text,options_json,correct_option,explanation,sort_order,created_at)
                    VALUES(?,?,?,'CONTEXT_MEANING',?,?,?,?,?,?,?)""",
                    (session_id, item["pointId"], item["targetNodeId"], item["context"], item["question"],
                     json.dumps(item["options"], ensure_ascii=False), item["correctOption"],
                     item["explanation"], order, now()))
            db.execute("UPDATE review_sessions SET status='READY',actual_question_count=? WHERE id=?", (len(questions), session_id))
            raise_after = False
    if raise_after:
        raise GenerationError("所有题目生成失败，请检查 AI 配置后重试。" + ("最近错误：" + errors[-1] if errors else ""))
    return get_session(session_id)


def get_session(session_id):
    with connect() as db:
        session = db.execute("SELECT * FROM review_sessions WHERE id=? AND user_id=1", (session_id,)).fetchone()
        if not session:
            return None
        questions = db.execute("""SELECT q.*,p.title,a.selected_option,a.is_correct,a.response_time_ms
            FROM review_questions q JOIN points p ON p.id=q.point_id
            LEFT JOIN review_attempts a ON a.question_id=q.id
            WHERE q.session_id=? ORDER BY q.sort_order""", (session_id,)).fetchall()
    result = dict(session)
    result["questions"] = []
    for row in questions:
        question = {"id": row["id"], "pointId": row["point_id"], "title": row["title"],
                    "context": row["context_text"], "question": row["prompt_text"],
                    "options": json.loads(row["options_json"]), "sortOrder": row["sort_order"]}
        if row["selected_option"]:
            question["answer"] = {"selectedOption": row["selected_option"],
                                  "isCorrect": bool(row["is_correct"]), "correctOption": row["correct_option"],
                                  "explanation": row["explanation"]}
        result["questions"].append(question)
    return result


def _settle(db, session_id, stamp):
    rows = db.execute("""SELECT a.id,a.point_id,a.is_correct,s.mastery,s.review_count,s.correct_count,
        s.wrong_count,s.correct_streak FROM review_attempts a
        JOIN point_review_states s ON s.point_id=a.point_id
        WHERE a.session_id=? ORDER BY a.id""", (session_id,)).fetchall()
    for row in rows:
        correct = bool(row["is_correct"])
        old = row["mastery"]
        mastery = (3 if correct else 1) if old is None else max(1, min(5, old + (1 if correct else -1)))
        days = 1 if not correct else {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}[mastery]
        next_at = (datetime.fromisoformat(stamp) + timedelta(days=days)).isoformat(timespec="seconds")
        db.execute("""UPDATE point_review_states SET mastery=?,last_reviewed_at=?,next_review_at=?,
            review_count=review_count+1,correct_count=correct_count+?,wrong_count=wrong_count+?,
            correct_streak=?,updated_at=? WHERE point_id=?""",
            (mastery, stamp, next_at, int(correct), int(not correct), row["correct_streak"] + 1 if correct else 0,
             stamp, row["point_id"]))
        db.execute("UPDATE review_attempts SET mastery_before=?,mastery_after=? WHERE id=?", (old, mastery, row["id"]))
    db.execute("UPDATE review_sessions SET status='COMPLETED',completed_at=? WHERE id=?", (stamp, session_id))


def answer(session_id, question_id, selected, response_time_ms=None):
    if selected not in ("A", "B", "C", "D"):
        raise InputError("请选择 A、B、C 或 D")
    if response_time_ms is not None and (not isinstance(response_time_ms, int) or response_time_ms < 0 or response_time_ms > 3_600_000):
        raise InputError("答题耗时无效")
    with transaction(immediate=True) as db:
        session = db.execute("SELECT * FROM review_sessions WHERE id=? AND user_id=1", (session_id,)).fetchone()
        if not session:
            return None
        if session["status"] not in ("READY", "IN_PROGRESS"):
            raise InputError("本轮复习当前不能答题")
        next_question = db.execute("""SELECT q.* FROM review_questions q
            LEFT JOIN review_attempts a ON a.question_id=q.id
            WHERE q.session_id=? AND a.id IS NULL ORDER BY q.sort_order LIMIT 1""", (session_id,)).fetchone()
        if not next_question or next_question["id"] != question_id:
            raise InputError("请按顺序作答，每道题只能提交一次")
        stamp = now()
        correct = selected == next_question["correct_option"]
        db.execute("""INSERT INTO review_attempts(session_id,question_id,point_id,selected_option,is_correct,response_time_ms,answered_at)
            VALUES(?,?,?,?,?,?,?)""", (session_id, question_id, next_question["point_id"], selected, int(correct), response_time_ms, stamp))
        if session["status"] == "READY":
            db.execute("UPDATE review_sessions SET status='IN_PROGRESS',started_at=? WHERE id=?", (stamp, session_id))
        remaining = db.execute("""SELECT COUNT(*) FROM review_questions q LEFT JOIN review_attempts a ON a.question_id=q.id
            WHERE q.session_id=? AND a.id IS NULL""", (session_id,)).fetchone()[0]
        if remaining == 0:
            _settle(db, session_id, stamp)
    return {"selectedOption": selected, "isCorrect": correct,
            "correctOption": next_question["correct_option"], "explanation": next_question["explanation"],
            "completed": remaining == 0}


def abandon(session_id):
    with transaction(immediate=True) as db:
        changed = db.execute("""UPDATE review_sessions SET status='ABANDONED'
            WHERE id=? AND user_id=1 AND status IN ('READY','IN_PROGRESS')""", (session_id,)).rowcount
    return bool(changed)


def result(session_id):
    with connect() as db:
        session = db.execute("SELECT * FROM review_sessions WHERE id=? AND user_id=1", (session_id,)).fetchone()
        if not session:
            return None
        if session["status"] != "COMPLETED":
            raise InputError("本轮复习尚未完成")
        attempts = db.execute("""SELECT p.id AS point_id,p.title,a.selected_option,a.is_correct,
            a.mastery_before,a.mastery_after,q.correct_option,q.explanation
            FROM review_attempts a JOIN points p ON p.id=a.point_id
            JOIN review_questions q ON q.id=a.question_id
            WHERE a.session_id=? ORDER BY q.sort_order""", (session_id,)).fetchall()
    items = [dict(row) for row in attempts]
    count = len(items)
    correct = sum(item["is_correct"] for item in items)
    return {"id": session_id, "completedAt": session["completed_at"], "total": count,
            "correct": correct, "wrong": count - correct,
            "accuracy": round(100 * correct / count) if count else 0, "items": items}
