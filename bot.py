import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent / "data.json"
PAGES_URL = os.environ.get("PAGES_URL", "")


def load_data() -> dict | None:
    if not DATA_FILE.exists():
        return None
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _status_label(status: int) -> str:
    return {1: "예정", 2: "접수중", 3: "당첨발표", 4: "완료"}.get(status, "-")


async def cmd_cheongak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    if not data or not data.get("apts"):
        await update.message.reply_text("청약 데이터가 없습니다. 업데이트 후 다시 시도해주세요.")
        return

    updated = (data.get("updatedAt") or "")[:10]
    apts = data["apts"]

    # 접수중(2) 먼저, 그 다음 예정(1) / 동일 상태면 청약일 순
    active = [a for a in apts if a.get("status") in (1, 2)]
    active.sort(key=lambda a: (0 if a.get("status") == 2 else 1, a.get("firstApplyDate") or "9999"))
    top = active[:5]

    lines = [f"🏠 <b>부산 청약 현황</b>  ({updated} 기준)\n"]
    for apt in top:
        badge = "🔴" if apt.get("status") == 2 else "🔵"
        lines.append(
            f"{badge} <b>{apt.get('name', '-')}</b>\n"
            f"  {apt.get('regionName', '')}  |  {_status_label(apt.get('status', 0))}  |  {apt.get('dDayText', '')}\n"
            f"  청약일: {apt.get('firstApplyDate') or '미정'}\n"
        )

    if PAGES_URL:
        lines.append(f"🔗 <a href='{PAGES_URL}'>전체 보기</a>")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def _start_health_server() -> None:
    """Railway health check용 최소 HTTP 서버."""
    port = int(os.environ.get("PORT", 8080))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, *args):
            pass

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다")

    threading.Thread(target=_start_health_server, daemon=True).start()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("청약", cmd_cheongak))

    logger.info("봇 시작 (polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
