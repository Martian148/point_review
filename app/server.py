import json
import mimetypes
import os
import re
from datetime import datetime, time, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from . import points, review
from .ai import GenerationError, configured
from .db import connect, init_db


STATIC = Path(__file__).resolve().parent.parent / "static"
LOCAL_TZ = ZoneInfo(os.environ.get("POINT_REVIEW_TIMEZONE", "Asia/Shanghai"))


def dashboard():
    with connect() as db:
        counts = db.execute("""SELECT COUNT(*) AS total,
            SUM(CASE WHEN s.mastery IS NULL THEN 1 ELSE 0 END) AS unevaluated
            FROM points p JOIN point_review_states s ON s.point_id=p.id
            WHERE p.user_id=1 AND p.deleted_at IS NULL""").fetchone()
        recent = [dict(row) for row in db.execute("""SELECT p.id,p.title,s.mastery,p.created_at
            FROM points p JOIN point_review_states s ON s.point_id=p.id
            WHERE p.user_id=1 AND p.deleted_at IS NULL ORDER BY p.created_at DESC,p.id DESC LIMIT 5""")]
        today = datetime.now(LOCAL_TZ).date()
        start = datetime.combine(today, time.min, LOCAL_TZ).astimezone(timezone.utc).isoformat(timespec="seconds")
        end = datetime.combine(today.fromordinal(today.toordinal()+1), time.min, LOCAL_TZ).astimezone(timezone.utc).isoformat(timespec="seconds")
        completed = db.execute("""SELECT COUNT(*) FROM review_attempts a JOIN review_sessions s ON s.id=a.session_id
            WHERE s.user_id=1 AND s.status='COMPLETED' AND a.answered_at>=? AND a.answered_at<?""", (start, end)).fetchone()[0]
        sessions = [dict(row) for row in db.execute("""SELECT id,status,actual_question_count,completed_at,created_at
            FROM review_sessions WHERE user_id=1 ORDER BY id DESC LIMIT 4""")]
    preview = review.review_preview()
    return {"total": counts["total"], "unevaluated": counts["unevaluated"] or 0,
            "due": preview["dueCount"], "completedToday": completed, "recentPoints": recent,
            "recentSessions": sessions, "aiConfigured": configured()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 1_000_000:
            raise points.InputError("请求内容为空或过长")
        try:
            value = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError) as exc:
            raise points.InputError("JSON 格式错误") from exc
        if not isinstance(value, dict):
            raise points.InputError("请求内容必须是对象")
        return value

    def dispatch(self):
        parsed = urlparse(self.path)
        path = parsed.path
        method = self.command
        if method == "GET" and not path.startswith("/api/"):
            return self.static(path)
        if method == "GET" and path == "/api/dashboard":
            return self.send_json(dashboard())
        if method == "GET" and path == "/api/points":
            return self.send_json(points.list_points(parse_qs(parsed.query).get("q", [""])[0]))
        match = re.fullmatch(r"/api/points/(\d+)", path)
        if match:
            point_id = int(match[1])
            if method == "GET":
                item = points.get_point(point_id)
                return self.send_json(item, 200 if item else 404)
            if method == "PUT":
                data = self.body()
                item = points.update_point(point_id, data.get("title"), data.get("nodes"))
                return self.send_json(item, 200 if item else 404)
            if method == "DELETE":
                return self.send_json({"deleted": points.delete_point(point_id)})
        if method == "POST" and path == "/api/points":
            data = self.body()
            return self.send_json(points.create_point(data.get("title"), data.get("nodes")), 201)
        if method == "POST" and path == "/api/import/preview":
            return self.send_json(points.preview_markdown(self.body().get("markdown")))
        if method == "POST" and path == "/api/import":
            return self.send_json(points.import_markdown(self.body().get("markdown")), 201)
        if method == "GET" and path == "/api/review/preview":
            return self.send_json(review.review_preview())
        if method == "POST" and path == "/api/review/sessions":
            return self.send_json(review.create_session(), 201)
        match = re.fullmatch(r"/api/review/sessions/(\d+)", path)
        if match and method == "GET":
            item = review.get_session(int(match[1]))
            return self.send_json(item, 200 if item else 404)
        match = re.fullmatch(r"/api/review/sessions/(\d+)/answers", path)
        if match and method == "POST":
            data = self.body()
            item = review.answer(int(match[1]), data.get("questionId"), data.get("selectedOption"), data.get("responseTimeMs"))
            return self.send_json(item, 200 if item else 404)
        match = re.fullmatch(r"/api/review/sessions/(\d+)/abandon", path)
        if match and method == "POST":
            return self.send_json({"abandoned": review.abandon(int(match[1]))})
        match = re.fullmatch(r"/api/review/sessions/(\d+)/result", path)
        if match and method == "GET":
            item = review.result(int(match[1]))
            return self.send_json(item, 200 if item else 404)
        return self.send_json({"error": "接口不存在"}, 404)

    def static(self, path):
        target = STATIC / ("index.html" if path == "/" or not Path(path).suffix else path.lstrip("/"))
        try:
            target = target.resolve()
            target.relative_to(STATIC)
            if not target.is_file():
                raise FileNotFoundError
            content = target.read_bytes()
        except (ValueError, FileNotFoundError):
            return self.send_json({"error": "页面不存在"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(target.name)[0] or "application/octet-stream") + ("; charset=utf-8" if target.suffix in (".html", ".css", ".js") else ""))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        self.safe_dispatch()

    def do_POST(self):
        self.safe_dispatch()

    def do_PUT(self):
        self.safe_dispatch()

    def do_DELETE(self):
        self.safe_dispatch()

    def safe_dispatch(self):
        try:
            self.dispatch()
        except points.InputError as exc:
            self.send_json({"error": str(exc)}, 400)
        except GenerationError as exc:
            self.send_json({"error": str(exc)}, 502)
        except Exception:
            import traceback
            traceback.print_exc()
            self.send_json({"error": "服务器遇到意外错误"}, 500)


def main():
    init_db()
    host = os.environ.get("POINT_REVIEW_HOST", "127.0.0.1")
    port = int(os.environ.get("POINT_REVIEW_PORT", "8000"))
    print(f"Point-review 已启动：http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
