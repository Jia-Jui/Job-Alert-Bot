from __future__ import annotations

from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from .config import AppConfig
from .db import JobStatusStore, SeenJobsStore, build_job_status_store, build_seen_jobs_store
from .models import APPLICATION_STATUSES, JobApplicationStatus, JobPosting
from .review import ACTIVE_PIPELINE_STATUSES, ReviewQueueItem, build_review_queue, group_status_board, normalize_status_alias

DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8765


@dataclass(frozen=True)
class DashboardData:
    queue: list[ReviewQueueItem]
    queue_total: int
    link_review_queue: list[ReviewQueueItem]
    link_review_total: int
    grouped_statuses: dict[str, list[JobApplicationStatus]]
    active_records: list[JobApplicationStatus]
    seen_jobs: list[JobPosting]
    seen_total: int
    status_by_key: dict[str, str]
    min_age_minutes: int
    queue_limit: int
    seen_limit: int
    storage_summary: str
    empty_reason: str | None


def serve_dashboard(config: AppConfig, host: str = DEFAULT_UI_HOST, port: int = DEFAULT_UI_PORT) -> None:
    handler_class = _build_handler(config)
    with ThreadingHTTPServer((host, port), handler_class) as server:
        print(f"Job Alert Bot UI running at http://{host}:{port}")
        print("Press Ctrl+C to stop.")
        server.serve_forever()


def _build_dashboard(
    config: AppConfig,
    seen_store: SeenJobsStore,
    status_store: JobStatusStore,
    min_age_minutes: int,
    queue_limit: int,
    seen_limit: int,
) -> DashboardData:
    statuses = status_store.list_statuses()
    status_by_key = {record.dedupe_key: record.status for record in statuses}
    seen_jobs = seen_store.list_seen_jobs()
    full_queue = build_review_queue(
        jobs=seen_jobs,
        statuses={record.dedupe_key: record for record in statuses},
        include_keywords=config.include_keywords,
        preferred_locations=config.preferred_locations,
        minimum_age_minutes=min_age_minutes,
    )
    link_review_queue = [item for item in full_queue if item.needs_link_review]
    grouped = group_status_board(statuses)
    active = [record for record in statuses if record.status in ACTIVE_PIPELINE_STATUSES]
    active.sort(key=lambda item: item.updated_at, reverse=True)

    if config.storage_mode == "sqlite":
        storage_summary = f"SQLite • {config.sqlite_db_path.resolve()}"
        empty_reason = None
        if not seen_jobs:
            empty_reason = (
                "No tracked jobs were found in the current SQLite database. "
                "If an older UI launch was started from another folder, it may have created a different empty jobs.db. "
                "This build now defaults to the repo database path shown above."
            )
    else:
        storage_summary = "Firebase Realtime Database • /seen_jobs and /job_statuses"
        empty_reason = None if seen_jobs else "No tracked jobs were found in the current Firebase data source."

    return DashboardData(
        queue=full_queue[:queue_limit],
        queue_total=len(full_queue),
        link_review_queue=link_review_queue[: min(queue_limit, 6)],
        link_review_total=len(link_review_queue),
        grouped_statuses=grouped,
        active_records=active,
        seen_jobs=seen_jobs[:seen_limit],
        seen_total=len(seen_jobs),
        status_by_key=status_by_key,
        min_age_minutes=min_age_minutes,
        queue_limit=queue_limit,
        seen_limit=seen_limit,
        storage_summary=storage_summary,
        empty_reason=empty_reason,
    )


def _build_handler(config: AppConfig) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._write_response(HTTPStatus.OK, "text/plain; charset=utf-8", b"ok")
                return
            if parsed.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            query = parse_qs(parsed.query)
            min_age = _parse_positive_int(query.get("min_age_minutes", ["60"])[0], 60)
            queue_limit = _parse_positive_int(query.get("queue_limit", ["24"])[0], 24)
            seen_limit = _parse_positive_int(query.get("seen_limit", ["40"])[0], 40)
            message = query.get("message", [""])[0]
            seen_store = build_seen_jobs_store(config)
            status_store = build_job_status_store(config)
            dashboard = _build_dashboard(config, seen_store, status_store, min_age, queue_limit, seen_limit)
            html = _render_dashboard(dashboard, message)
            self._write_response(HTTPStatus.OK, "text/html; charset=utf-8", html.encode("utf-8"))

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/status":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            form = parse_qs(body)
            dedupe_key = form.get("dedupe_key", [""])[0].strip()
            status_value = form.get("status", [""])[0].strip()
            min_age = _parse_positive_int(form.get("min_age_minutes", ["60"])[0], 60)
            queue_limit = _parse_positive_int(form.get("queue_limit", ["24"])[0], 24)
            seen_limit = _parse_positive_int(form.get("seen_limit", ["40"])[0], 40)

            try:
                if not dedupe_key:
                    raise ValueError("Missing dedupe key.")
                normalized = normalize_status_alias(status_value)
                status_store = build_job_status_store(config)
                status_store.set_status(dedupe_key, normalized)
                message = f"Updated {dedupe_key} to {normalized}."
            except ValueError as exc:
                message = str(exc)

            target = "/?" + urlencode(
                {
                    "min_age_minutes": str(min_age),
                    "queue_limit": str(queue_limit),
                    "seen_limit": str(seen_limit),
                    "message": message,
                }
            )
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", target)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_response(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler


def _render_dashboard(data: DashboardData, message: str) -> str:
    flash = f'<div class="flash">{escape(message)}</div>' if message else ""
    empty_banner = (
        '<section class="diagnostic reveal">'
        '<div class="diagnostic-copy">'
        '<span class="diagnostic-eyebrow">No tracked jobs loaded</span>'
        f'<h2>{escape(data.empty_reason or "")}</h2>'
        "<p>Check the data source badge below. If you were launching the UI from a different folder before, restart the server and open this branch again.</p>"
        "</div></section>"
        if data.empty_reason
        else ""
    )
    queue_cards = "".join(
        _render_queue_card(item, data.min_age_minutes, data.queue_limit, data.seen_limit) for item in data.queue
    ) or '<div class="empty-grid">No review queue jobs match the current filters.</div>'
    link_review_cards = "".join(
        _render_queue_card(item, data.min_age_minutes, data.queue_limit, data.seen_limit)
        for item in data.link_review_queue
    ) or '<div class="empty-grid">No uncertain-link jobs need manual review right now.</div>'
    active_cards = "".join(
        _render_status_card(record, data.min_age_minutes, data.queue_limit, data.seen_limit, accent="active")
        for record in data.active_records
    ) or '<div class="empty-grid">No active pipeline jobs yet.</div>'
    board_columns = "".join(
        _render_board_column(
            status_name,
            data.grouped_statuses.get(status_name, []),
            data.min_age_minutes,
            data.queue_limit,
            data.seen_limit,
        )
        for status_name in APPLICATION_STATUSES
    )
    seen_rows = "".join(_render_seen_row(job, data.status_by_key) for job in data.seen_jobs) or (
        '<tr><td colspan="5" class="empty-row">No seen jobs found.</td></tr>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Alert Bot Review Studio</title>
  <style>
    :root {{
      --bg: #07111f;
      --bg-soft: #0d1728;
      --panel: rgba(16, 24, 39, 0.78);
      --panel-solid: #0f1b2f;
      --panel-strong: #13233c;
      --line: rgba(148, 163, 184, 0.18);
      --line-strong: rgba(148, 163, 184, 0.28);
      --text: #ecf3ff;
      --muted: #8ca0bf;
      --accent: #5fa8ff;
      --accent-2: #34d399;
      --accent-3: #ff7e67;
      --accent-4: #8b5cf6;
      --warning: rgba(255, 201, 107, 0.16);
      --warning-line: rgba(255, 201, 107, 0.36);
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
      --radius-xl: 28px;
      --radius-lg: 22px;
      --radius-md: 18px;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--text);
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      background:
        radial-gradient(circle at 10% 10%, rgba(95, 168, 255, 0.22), transparent 24%),
        radial-gradient(circle at 85% 15%, rgba(52, 211, 153, 0.16), transparent 26%),
        radial-gradient(circle at 50% 100%, rgba(139, 92, 246, 0.12), transparent 30%),
        linear-gradient(180deg, #050c16 0%, var(--bg) 42%, #091321 100%);
      min-height: 100vh;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    code {{
      font-family: Consolas, "SFMono-Regular", monospace;
      font-size: 0.86rem;
      color: #cfe1ff;
      word-break: break-all;
    }}
    .shell {{
      width: min(1500px, calc(100% - 32px));
      margin: 24px auto 48px;
      position: relative;
    }}
    .shell::before,
    .shell::after {{
      content: "";
      position: fixed;
      inset: auto;
      width: 360px;
      height: 360px;
      border-radius: 999px;
      filter: blur(70px);
      opacity: 0.35;
      pointer-events: none;
      z-index: 0;
      animation: drift 18s ease-in-out infinite;
    }}
    .shell::before {{
      background: rgba(95, 168, 255, 0.18);
      top: 90px;
      left: -80px;
    }}
    .shell::after {{
      background: rgba(139, 92, 246, 0.14);
      right: -60px;
      top: 340px;
      animation-duration: 22s;
    }}
    .reveal {{
      animation: float-in 560ms ease both;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 34px;
      background:
        linear-gradient(135deg, rgba(18, 28, 48, 0.94), rgba(11, 20, 35, 0.88)),
        linear-gradient(180deg, rgba(95, 168, 255, 0.08), rgba(52, 211, 153, 0.06));
      box-shadow: var(--shadow);
      z-index: 1;
    }}
    .hero::before {{
      content: "";
      position: absolute;
      inset: -40% auto auto -10%;
      width: 420px;
      height: 420px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(95, 168, 255, 0.26), transparent 66%);
      animation: pulse 14s ease-in-out infinite;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -12% -42% auto;
      width: 520px;
      height: 520px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(52, 211, 153, 0.16), transparent 66%);
      animation: pulse 18s ease-in-out infinite reverse;
    }}
    .hero-grid {{
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(340px, 0.9fr);
      gap: 20px;
      padding: 30px;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.74rem;
      color: #9ec5ff;
      font-weight: 700;
      margin-bottom: 12px;
    }}
    .eyebrow::before {{
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      box-shadow: 0 0 16px rgba(95, 168, 255, 0.7);
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2.5rem, 4vw, 4.5rem);
      line-height: 0.94;
      letter-spacing: -0.05em;
      max-width: 12ch;
    }}
    .hero-copy {{
      margin: 18px 0 0;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.75;
      max-width: 60ch;
    }}
    .hero-meta {{
      margin-top: 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .meta-chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: #d5e3ff;
      font-size: 0.92rem;
    }}
    .hero-side {{
      display: grid;
      gap: 16px;
    }}
    .glass-panel {{
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(10, 18, 31, 0.64);
      backdrop-filter: blur(16px);
      border-radius: var(--radius-xl);
      padding: 18px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .stat {{
      border-radius: var(--radius-md);
      padding: 16px;
      background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
      border: 1px solid rgba(255, 255, 255, 0.06);
      transition: transform 180ms ease, border-color 180ms ease;
    }}
    .stat:hover {{
      transform: translateY(-2px);
      border-color: rgba(95, 168, 255, 0.38);
    }}
    .stat strong {{
      display: block;
      font-size: 1.9rem;
      letter-spacing: -0.05em;
      margin-bottom: 6px;
    }}
    .stat span {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .control-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 8px;
    }}
    .field label {{
      display: block;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #86a1c6;
      margin-bottom: 8px;
    }}
    .field input {{
      width: 100%;
      border: 1px solid rgba(255, 255, 255, 0.10);
      background: rgba(3, 8, 16, 0.78);
      color: var(--text);
      border-radius: 14px;
      padding: 12px 14px;
      outline: none;
      transition: border-color 180ms ease, box-shadow 180ms ease;
    }}
    .field input:focus {{
      border-color: rgba(95, 168, 255, 0.6);
      box-shadow: 0 0 0 3px rgba(95, 168, 255, 0.18);
    }}
    .button-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }}
    button, .button {{
      appearance: none;
      border: none;
      border-radius: 999px;
      padding: 12px 16px;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
      letter-spacing: 0.01em;
      transition: transform 180ms ease, box-shadow 180ms ease, opacity 180ms ease;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }}
    button:hover, .button:hover {{
      transform: translateY(-1px);
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
    }}
    .button-primary {{
      background: linear-gradient(135deg, var(--accent), #3b82f6);
      color: white;
    }}
    .button-secondary {{
      background: rgba(255, 255, 255, 0.06);
      color: var(--text);
      border: 1px solid rgba(255, 255, 255, 0.09);
    }}
    .button-apply {{
      background: linear-gradient(135deg, var(--accent-2), #10b981);
      color: #04130e;
    }}
    .button-danger {{
      background: rgba(255, 126, 103, 0.16);
      color: #ffc3b8;
      border: 1px solid rgba(255, 126, 103, 0.18);
    }}
    .flash {{
      margin-top: 18px;
      background: var(--warning);
      border: 1px solid var(--warning-line);
      color: #f8dc9d;
      border-radius: 16px;
      padding: 14px 16px;
    }}
    .diagnostic {{
      margin-top: 18px;
      padding: 22px;
      border-radius: 24px;
      border: 1px solid rgba(255, 126, 103, 0.18);
      background: linear-gradient(135deg, rgba(255, 126, 103, 0.08), rgba(255, 201, 107, 0.06));
      box-shadow: var(--shadow);
    }}
    .diagnostic-eyebrow {{
      display: inline-block;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #ffb8aa;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .diagnostic h2 {{
      margin: 0 0 8px;
      font-size: 1.25rem;
      letter-spacing: -0.02em;
    }}
    .diagnostic p {{
      margin: 0;
      color: #d5c8af;
      line-height: 1.7;
    }}
    .toolbar {{
      margin-top: 22px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
    }}
    .search-shell {{
      flex: 1 1 280px;
      min-width: 260px;
    }}
    .search-shell input {{
      width: 100%;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(8, 14, 25, 0.82);
      color: var(--text);
      padding: 14px 16px;
      outline: none;
    }}
    .search-shell input:focus {{
      border-color: rgba(95, 168, 255, 0.5);
      box-shadow: 0 0 0 3px rgba(95, 168, 255, 0.15);
    }}
    .toolbar-note {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    section {{
      position: relative;
      z-index: 1;
      margin-top: 22px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 28px;
      background: rgba(10, 16, 27, 0.78);
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(16px);
    }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: end;
      padding: 22px 24px 18px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }}
    .section-head h2 {{
      margin: 0;
      font-size: 1.35rem;
      letter-spacing: -0.03em;
    }}
    .section-head p {{
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .section-badge {{
      padding: 10px 14px;
      border-radius: 999px;
      color: #d3e4ff;
      background: rgba(95, 168, 255, 0.12);
      border: 1px solid rgba(95, 168, 255, 0.18);
      font-size: 0.9rem;
      white-space: nowrap;
    }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      padding: 18px 24px 24px;
    }}
    .job-card {{
      position: relative;
      overflow: hidden;
      border-radius: 22px;
      padding: 18px;
      background: linear-gradient(180deg, rgba(18, 28, 48, 0.92), rgba(12, 20, 34, 0.94));
      border: 1px solid rgba(255, 255, 255, 0.08);
      transition: transform 220ms ease, border-color 220ms ease, box-shadow 220ms ease;
      animation: float-in 520ms ease both;
    }}
    .job-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(125deg, rgba(95, 168, 255, 0.10), transparent 30%, rgba(52, 211, 153, 0.08) 100%);
      pointer-events: none;
    }}
    .job-card:hover {{
      transform: translateY(-4px);
      border-color: rgba(95, 168, 255, 0.34);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.28);
    }}
    .job-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      position: relative;
      z-index: 1;
    }}
    .job-title {{
      margin: 0;
      font-size: 1.08rem;
      line-height: 1.35;
      letter-spacing: -0.02em;
    }}
    .job-company {{
      color: #d9e6ff;
      font-weight: 700;
      margin-bottom: 4px;
    }}
    .job-meta {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.6;
      position: relative;
      z-index: 1;
    }}
    .job-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
      position: relative;
      z-index: 1;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #d8e6ff;
      font-size: 0.86rem;
    }}
    .pill.emphasis {{
      background: rgba(95, 168, 255, 0.14);
      border-color: rgba(95, 168, 255, 0.22);
      color: #beddff;
    }}
    .pill.success {{
      background: rgba(52, 211, 153, 0.14);
      border-color: rgba(52, 211, 153, 0.22);
      color: #aef1d5;
    }}
    .status-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
      position: relative;
      z-index: 1;
    }}
    .status-actions form {{
      margin: 0;
    }}
    .status-actions button {{
      padding: 10px 12px;
      font-size: 0.9rem;
    }}
    .board-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      padding: 18px 24px 24px;
    }}
    .board-column {{
      border-radius: 24px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: linear-gradient(180deg, rgba(17, 26, 42, 0.9), rgba(11, 18, 31, 0.92));
      padding: 16px;
      min-height: 220px;
    }}
    .board-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .board-head h3 {{
      margin: 0;
      text-transform: capitalize;
      font-size: 1rem;
    }}
    .board-count {{
      min-width: 36px;
      height: 36px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #dce8ff;
      font-weight: 700;
    }}
    .mini-card {{
      border-radius: 18px;
      padding: 14px;
      margin-top: 12px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.06);
    }}
    .mini-card:first-of-type {{
      margin-top: 0;
    }}
    .mini-card small {{
      color: var(--muted);
      display: block;
      margin-top: 6px;
      line-height: 1.55;
    }}
    .table-wrap {{
      overflow: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 14px 16px;
      text-align: left;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      vertical-align: top;
    }}
    th {{
      color: #9ab1d4;
      font-size: 0.86rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    td {{
      color: #dfebff;
      font-size: 0.95rem;
    }}
    .empty-grid {{
      margin: 0 24px 24px;
      border-radius: 20px;
      border: 1px dashed rgba(255, 255, 255, 0.12);
      background: rgba(255, 255, 255, 0.02);
      color: var(--muted);
      text-align: center;
      padding: 36px 20px;
      font-style: italic;
    }}
    .empty-row {{
      color: var(--muted);
      text-align: center;
      font-style: italic;
      padding: 28px 16px;
    }}
    .muted {{
      color: var(--muted);
    }}
    .data-source {{
      margin-top: 16px;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.6;
    }}
    .data-source strong {{
      color: #dce8ff;
    }}
    .js-filter-empty {{
      display: none;
      margin-top: 12px;
      color: var(--muted);
      font-style: italic;
    }}
    @keyframes drift {{
      0%, 100% {{ transform: translate3d(0, 0, 0); }}
      50% {{ transform: translate3d(24px, -18px, 0); }}
    }}
    @keyframes pulse {{
      0%, 100% {{ transform: scale(1); opacity: 0.8; }}
      50% {{ transform: scale(1.15); opacity: 1; }}
    }}
    @keyframes float-in {{
      from {{
        opacity: 0;
        transform: translateY(18px) scale(0.985);
      }}
      to {{
        opacity: 1;
        transform: translateY(0) scale(1);
      }}
    }}
    @media (max-width: 1100px) {{
      .hero-grid,
      .card-grid,
      .board-grid {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      .shell {{
        width: min(100% - 16px, 100%);
        margin-top: 16px;
      }}
      .hero-grid,
      .section-head,
      .card-grid,
      .board-grid {{
        padding-left: 16px;
        padding-right: 16px;
      }}
      .hero-grid {{
        padding-top: 22px;
        padding-bottom: 22px;
      }}
      .stats,
      .control-grid {{
        grid-template-columns: 1fr;
      }}
      .toolbar {{
        flex-direction: column;
        align-items: stretch;
      }}
      .section-head {{
        align-items: start;
        flex-direction: column;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero reveal">
      <div class="hero-grid">
        <div>
          <div class="eyebrow">Review Studio</div>
          <h1>Run your job search like a focused command center.</h1>
          <p class="hero-copy">Review stronger matches, surface uncertain apply links, and move jobs through your pipeline with one click. This dashboard stays local-first and keeps the scheduled bot separate from your manual application sessions.</p>
          <div class="hero-meta">
            <span class="meta-chip">Queue threshold: {data.min_age_minutes} minutes</span>
            <span class="meta-chip">Showing {len(data.queue)} of {data.queue_total} queue jobs</span>
            <span class="meta-chip">Needs link review: {data.link_review_total}</span>
            <span class="meta-chip">Showing {len(data.seen_jobs)} of {data.seen_total} tracked jobs</span>
          </div>
          {flash}
        </div>
        <div class="hero-side">
          <div class="glass-panel">
            <div class="stats">
              <div class="stat">
                <strong>{data.queue_total}</strong>
                <span>Queue candidates</span>
              </div>
              <div class="stat">
                <strong>{len(data.active_records)}</strong>
                <span>Active pipeline</span>
              </div>
              <div class="stat">
                <strong>{data.seen_total}</strong>
                <span>Tracked jobs</span>
              </div>
            </div>
          </div>
          <div class="glass-panel">
            <form method="get" action="/">
              <div class="control-grid">
                <div class="field">
                  <label for="min_age_minutes">Queue Age</label>
                  <input id="min_age_minutes" name="min_age_minutes" type="number" min="0" value="{data.min_age_minutes}">
                </div>
                <div class="field">
                  <label for="queue_limit">Queue Rows</label>
                  <input id="queue_limit" name="queue_limit" type="number" min="1" value="{data.queue_limit}">
                </div>
                <div class="field">
                  <label for="seen_limit">Seen Rows</label>
                  <input id="seen_limit" name="seen_limit" type="number" min="1" value="{data.seen_limit}">
                </div>
              </div>
              <div class="button-row">
                <button type="submit" class="button-primary">Refresh Dashboard</button>
                <a href="#review-queue" class="button button-secondary">Jump to Queue</a>
              </div>
            </form>
            <div class="data-source"><strong>Data source:</strong> {escape(data.storage_summary)}</div>
          </div>
        </div>
      </div>
    </section>

    {empty_banner}

    <div class="toolbar reveal">
      <div class="button-row">
        <a href="#link-review" class="button button-secondary">Needs Link Review</a>
        <a href="#review-queue" class="button button-secondary">Queue</a>
        <a href="#active-pipeline" class="button button-secondary">Active</a>
        <a href="#status-board" class="button button-secondary">Board</a>
        <a href="#seen-jobs" class="button button-secondary">Seen Jobs</a>
      </div>
      <div class="search-shell">
        <input id="job-search" type="search" placeholder="Search company, role, location, or dedupe key">
      </div>
      <div class="toolbar-note">The browser console error you mentioned is usually a browser extension message-channel issue, not a failure from this local page.</div>
    </div>

    <section id="link-review" class="reveal">
      <div class="section-head">
        <div>
          <h2>Needs Link Review</h2>
          <p>These jobs still look promising, but their best apply path is low-confidence. This is the fastest place to sanity-check the link before you apply.</p>
        </div>
        <div class="section-badge">{len(data.link_review_queue)} showing / {data.link_review_total} total</div>
      </div>
      <div class="card-grid js-filter-scope" data-empty-id="link-review-empty">
        {link_review_cards}
      </div>
      <div id="link-review-empty" class="empty-grid js-filter-empty">No uncertain-link jobs match the current search.</div>
    </section>

    <section id="review-queue" class="reveal">
      <div class="section-head">
        <div>
          <h2>Review Queue</h2>
          <p>Jobs older than {data.min_age_minutes} minutes that are still un-applied. This is the manual apply queue you run when you are ready to work through openings.</p>
        </div>
        <div class="section-badge">Showing {len(data.queue)} of {data.queue_total}</div>
      </div>
      <div class="card-grid js-filter-scope" data-empty-id="queue-empty">
        {queue_cards}
      </div>
      <div id="queue-empty" class="empty-grid js-filter-empty">No queue cards match the current search.</div>
    </section>

    <section id="active-pipeline" class="reveal">
      <div class="section-head">
        <div>
          <h2>Active Pipeline</h2>
          <p>Applications already in motion: applied, interview, in progress, and offer.</p>
        </div>
        <div class="section-badge">{len(data.active_records)} active jobs</div>
      </div>
      <div class="card-grid js-filter-scope" data-empty-id="active-empty">
        {active_cards}
      </div>
      <div id="active-empty" class="empty-grid js-filter-empty">No active jobs match the current search.</div>
    </section>

    <section id="status-board" class="reveal">
      <div class="section-head">
        <div>
          <h2>Status Board</h2>
          <p>Every tracked status grouped into a simple board, so changing progress is one click away.</p>
        </div>
        <div class="section-badge">{sum(len(records) for records in data.grouped_statuses.values())} status records</div>
      </div>
      <div class="board-grid js-filter-scope" data-empty-id="board-empty">
        {board_columns}
      </div>
      <div id="board-empty" class="empty-grid js-filter-empty">No status cards match the current search.</div>
    </section>

    <section id="seen-jobs" class="reveal">
      <div class="section-head">
        <div>
          <h2>Seen Jobs Snapshot</h2>
          <p>Quick lookup view over the tracked jobs, useful when you want to confirm what is already in the store.</p>
        </div>
        <div class="section-badge">Showing {len(data.seen_jobs)} of {data.seen_total}</div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Role</th>
              <th>Location</th>
              <th>Dedupe Key</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody id="seen-table-body">
            {seen_rows}
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <script>
    const searchInput = document.getElementById('job-search');

    function applyFilter() {{
      const query = (searchInput.value || '').trim().toLowerCase();
      document.querySelectorAll('.js-filter-scope').forEach((scope) => {{
        const items = Array.from(scope.querySelectorAll('.js-filter-item'));
        let visibleCount = 0;
        items.forEach((item) => {{
          const haystack = (item.dataset.search || '').toLowerCase();
          const match = !query || haystack.includes(query);
          item.style.display = match ? '' : 'none';
          if (match) visibleCount += 1;
        }});
        const emptyId = scope.dataset.emptyId;
        if (emptyId) {{
          const emptyNode = document.getElementById(emptyId);
          if (emptyNode) emptyNode.style.display = visibleCount === 0 ? 'block' : 'none';
        }}
      }});

      const seenRows = Array.from(document.querySelectorAll('#seen-table-body .js-filter-row'));
      let seenVisible = 0;
      seenRows.forEach((row) => {{
        const haystack = (row.dataset.search || '').toLowerCase();
        const match = !query || haystack.includes(query);
        row.style.display = match ? '' : 'none';
        if (match) seenVisible += 1;
      }});
    }}

    if (searchInput) {{
      searchInput.addEventListener('input', applyFilter);
      applyFilter();
    }}
  </script>
</body>
</html>"""


def _render_queue_card(item: ReviewQueueItem, min_age_minutes: int, queue_limit: int, seen_limit: int) -> str:
    job = item.job
    status_label = item.status or ("needs link review" if item.needs_link_review else "untracked")
    confidence_label = job.link_confidence or "unknown"
    confidence_class = " success" if confidence_label == "high" else ""
    manual_link_pill = '<span class="pill">needs manual link check</span>' if item.needs_link_review else ""
    search_value = " ".join(
        value
        for value in (job.company, job.title, job.location, job.dedupe_key, job.link, status_label, confidence_label)
        if value
    )
    return (
        f'<article class="job-card js-filter-item" data-search="{escape(search_value)}">'
        '<div class="job-top">'
        f'<div><div class="job-company">{escape(job.company)}</div><h3 class="job-title">{escape(job.title)}</h3></div>'
        f'<span class="pill emphasis">{escape(status_label)}</span>'
        '</div>'
        f'<div class="job-meta">{escape(job.location)}<br><code>{escape(job.dedupe_key)}</code><br><a href="{escape(job.best_apply_url or job.link)}" target="_blank" rel="noreferrer">Open best apply link</a></div>'
        '<div class="job-tags">'
        f'<span class="pill emphasis">score {item.score}</span>'
        f'<span class="pill">{item.age_minutes if item.age_minutes is not None else "?"}m old</span>'
        f'<span class="pill{confidence_class}">{escape(confidence_label)} link</span>'
        f"{manual_link_pill}"
        f'<span class="pill">manual queue</span>'
        '</div>'
        f'<div class="job-meta">{escape(item.reason or "Reason unavailable.")}</div>'
        f'{_render_status_actions(job.dedupe_key, min_age_minutes, queue_limit, seen_limit, ("applied", "saved", "rejected", "closed"))}'
        '</article>'
    )


def _render_status_card(
    record: JobApplicationStatus,
    min_age_minutes: int,
    queue_limit: int,
    seen_limit: int,
    accent: str,
) -> str:
    search_value = " ".join(
        value for value in (record.company, record.title, record.location, record.dedupe_key, record.status, record.link) if value
    )
    status_class = "success" if record.status in ACTIVE_PIPELINE_STATUSES else "emphasis"
    link_html = (
        f'<a href="{escape(record.best_apply_url or record.link)}" target="_blank" rel="noreferrer">Open best apply link</a>'
        if (record.best_apply_url or record.link)
        else '<span class="muted">No link saved</span>'
    )
    return (
        f'<article class="job-card js-filter-item" data-search="{escape(search_value)}">'
        '<div class="job-top">'
        f'<div><div class="job-company">{escape(record.company or "-")}</div><h3 class="job-title">{escape(record.title or "-")}</h3></div>'
        f'<span class="pill {status_class}">{escape(record.status)}</span>'
        '</div>'
        f'<div class="job-meta">{escape(record.location or "-")}<br><code>{escape(record.dedupe_key)}</code><br>{escape(record.updated_at.isoformat())}<br>{link_html}<br>{escape(record.rank_reason or "Reason unavailable.")}</div>'
        f'{_render_status_actions(record.dedupe_key, min_age_minutes, queue_limit, seen_limit, ("interview", "in-progress", "offer", "rejected", "closed"))}'
        '</article>'
    )


def _render_board_column(
    status_name: str,
    records: list[JobApplicationStatus],
    min_age_minutes: int,
    queue_limit: int,
    seen_limit: int,
) -> str:
    cards = "".join(
        _render_board_card(record, min_age_minutes, queue_limit, seen_limit) for record in records
    ) or '<div class="mini-card"><div class="muted">No jobs here yet.</div></div>'
    search_value = " ".join(
        " ".join(value for value in (record.company, record.title, record.location, record.dedupe_key, record.status) if value)
        for record in records
    )
    return (
        f'<div class="board-column js-filter-item" data-search="{escape(search_value)}">'
        '<div class="board-head">'
        f'<h3>{escape(status_name)}</h3>'
        f'<span class="board-count">{len(records)}</span>'
        '</div>'
        f'{cards}'
        '</div>'
    )


def _render_board_card(record: JobApplicationStatus, min_age_minutes: int, queue_limit: int, seen_limit: int) -> str:
    link_html = (
        f'<a href="{escape(record.best_apply_url or record.link)}" target="_blank" rel="noreferrer">Open best apply link</a>'
        if (record.best_apply_url or record.link)
        else '<span class="muted">No link saved</span>'
    )
    return (
        '<div class="mini-card">'
        f'<div class="job-company">{escape(record.company or "-")}</div>'
        f'<div class="job-title">{escape(record.title or "-")}</div>'
        f'<small>{escape(record.location or "-")}<br>{escape(record.updated_at.isoformat())}<br><code>{escape(record.dedupe_key)}</code><br>{link_html}<br>{escape(record.rank_reason or "Reason unavailable.")}</small>'
        f'{_render_status_actions(record.dedupe_key, min_age_minutes, queue_limit, seen_limit, ("saved", "applied", "interview", "in-progress", "rejected", "offer", "closed"))}'
        '</div>'
    )


def _render_seen_row(job: JobPosting, status_by_key: dict[str, str]) -> str:
    status_value = status_by_key.get(job.dedupe_key, "-")
    search_value = " ".join(value for value in (status_value, job.company, job.title, job.location, job.dedupe_key, job.link) if value)
    return (
        f'<tr class="js-filter-row" data-search="{escape(search_value)}">'
        f'<td><span class="pill">{escape(status_value)}</span></td>'
        f'<td><div class="job-company">{escape(job.company)}</div><div class="muted">{escape(job.title)}</div></td>'
        f'<td>{escape(job.location)}</td>'
        f'<td><code>{escape(job.dedupe_key)}</code></td>'
        f'<td><a href="{escape(job.best_apply_url or job.link)}" target="_blank" rel="noreferrer">Open best apply link</a></td>'
        '</tr>'
    )


def _render_status_actions(
    dedupe_key: str,
    min_age_minutes: int,
    queue_limit: int,
    seen_limit: int,
    primary: tuple[str, ...],
) -> str:
    buttons = []
    for status_name in primary:
        label = "in progress" if status_name == "in-progress" else status_name
        class_name = "button-secondary"
        if status_name in {"applied", "interview", "offer"}:
            class_name = "button-apply"
        elif status_name in {"rejected", "closed"}:
            class_name = "button-danger"
        buttons.append(
            '<form method="post" action="/status">'
            f'<input type="hidden" name="dedupe_key" value="{escape(dedupe_key)}">'
            f'<input type="hidden" name="status" value="{escape(status_name)}">'
            f'<input type="hidden" name="min_age_minutes" value="{min_age_minutes}">'
            f'<input type="hidden" name="queue_limit" value="{queue_limit}">'
            f'<input type="hidden" name="seen_limit" value="{seen_limit}">'
            f'<button type="submit" class="{class_name}">{escape(label)}</button>'
            '</form>'
        )
    return '<div class="status-actions">' + "".join(buttons) + "</div>"


def _parse_positive_int(raw: str, default: int) -> int:
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default
