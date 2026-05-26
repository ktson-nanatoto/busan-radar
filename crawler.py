"""
crawler.py — 호갱노노 부산 청약 데이터 크롤러
- 목록 수집: API 직접 호출 (requests) → 전체 페이지 수집
- 상세 수집: Selenium → 상위 10개 단지 상세 정보
 
실행:
    python crawler.py              # 목록 + 상세 (약 2~3분)
    python crawler.py --no-detail  # 목록만 (약 10~20초)
결과: data.json 저장
"""
 
import re
import json
import time
import logging
import argparse
import requests
from datetime import datetime
from pathlib import Path
 
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
 
# ── 설정 ──────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "data.json"
LOG_FILE    = BASE_DIR / "crawler.log"
 
BUSAN_REGION_CODE = "26"
API_BASE_URL = "https://hogangnono.com/api/v2/offers"
API_PARAMS = {
    "regionCode": BUSAN_REGION_CODE,
    "offerType": "commercial",
    "x": "129.0722829",   # 부산 중심 경도
    "y": "35.1524736",    # 부산 중심 위도
}
API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://hogangnono.com/",
    "Accept": "application/json",
}
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)
 
 
# ── Selenium 드라이버 ─────────────────────────────
def make_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)
 
 
# ── API 직접 호출로 전체 목록 수집 ────────────────
def fetch_all_apts_api() -> list:
    """
    Selenium 없이 API 직접 호출.
    페이지네이션으로 부산 전체 분양 예정 단지 수집.
    """
    apts = []
    page = 1
 
    while True:
        params = {**API_PARAMS, "page": page}
        log.info("API 호출 page=%d", page)
 
        try:
            res = requests.get(
                API_BASE_URL,
                params=params,
                headers=API_HEADERS,
                timeout=10
            )
 
            if res.status_code != 200:
                log.warning("API 응답 실패: %d — 종료", res.status_code)
                break
 
            body = res.json()
 
            if body.get("status") != "success":
                log.warning("API 상태 실패: %s", body.get("status"))
                break
 
            data  = body.get("data", {})
            items = data.get("data", [])
 
            if not items:
                log.info("데이터 없음 — 수집 완료")
                break
 
            # 부산 단지만 필터 (offerRegion이 26으로 시작)
            busan_items = [
                item for item in items
                if str(item.get("apt", {}).get("offerRegion", "")).startswith(BUSAN_REGION_CODE)
            ]
 
            # apt 필드를 상위로 끌어올려 flat 구조로 변환
            parsed = []
            for item in busan_items:
                apt = item.get("apt", {})
                parsed.append({
                    "hash":        apt.get("hash"),
                    "name":        apt.get("name"),
                    "regionName":  apt.get("regionName"),
                    "viewCount":   apt.get("viewCount", 0),
                    "alarmCount":  apt.get("offerSubscriptionCount", 0),
                    "status":      apt.get("status"),       # 1=예정 2=접수중 3=당첨발표 4=완료
                    "dateText":    item.get("dateText"),
                    "dDayText":    item.get("dDayText"),
                    "apt2youId":   item.get("apt2youId"),
                    "competition": item.get("avgCompetitionRate"),
                    "offerDate":   item.get("offerDate", "")[:10] if item.get("offerDate") else None,
                    "firstApplyDate": item.get("firstApplyDate", "")[:10] if item.get("firstApplyDate") else None,
                })
 
            apts.extend(parsed)
            log.info(
                "page=%d → 전체 %d개 중 부산 %d개 (누적 %d개)",
                page, len(items), len(busan_items), len(apts)
            )
 
            # 마지막 페이지 확인
            if data.get("isEnd", True):
                log.info("마지막 페이지 도달 — 목록 수집 완료")
                break
 
            page += 1
            time.sleep(0.5)  # 서버 부하 방지
 
        except requests.exceptions.Timeout:
            log.warning("타임아웃 page=%d — 재시도 없이 종료", page)
            break
        except Exception as e:
            log.warning("API 호출 실패 page=%d: %s", page, e)
            break
 
    return apts
 
 
# ── Selenium으로 상세 페이지 파싱 ─────────────────
def parse_detail(html: str) -> dict:
    """단지 상세 페이지에서 추가 정보 추출"""
    detail = {}
 
    # 공급 정보 테이블 (공급위치/규모/건설사/시행사/전화)
    table = re.search(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    if table:
        cells = re.findall(r'<t[dh][^>]*>\s*([^<\s][^<]*?)\s*</t[dh]>', table.group(1))
        for i in range(0, len(cells) - 1, 2):
            detail[cells[i].strip()] = cells[i+1].strip()
 
    # 좌표
    lat = re.search(r'"lat":([\d.]+)', html)
    lng = re.search(r'"lng":([\d.]+)', html)
    if lat:
        detail["lat"] = float(lat.group(1))
        detail["lng"] = float(lng.group(1)) if lng else None
 
    # 입주 예정 시기
    move_in = re.findall(r'(20\d\d년\s*\d+월)', html)
    detail["moveInDates"] = list(set(move_in))[:4]
 
    # 리뷰 (React Query JSON에서 추출)
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    big = max(scripts, key=lambda s: len(s.strip()), default="")
    try:
        data = json.loads(big.strip())
        for q in data.get("queryState", {}).get("queries", []):
            qk = q.get("queryKey", [{}])
            d  = q["state"].get("data")
            if d and "review" in str(qk) and "target" in str(qk):
                pages = d.get("pages", [{}])
                if pages:
                    detail["reviewCount"] = pages[0].get("total", 0)
                    detail["recentReviews"] = [
                        {
                            "name":    r.get("name", ""),
                            "content": r.get("content", "")[:80],
                            "up":      r.get("countUp", 0),
                        }
                        for r in pages[0].get("data", [])[:5]
                    ]
    except Exception:
        pass
 
    # 관련 뉴스
    news = re.findall(
        r'"title":"([^"]+)","pressName":"([^"]+)".*?"articleUrl":"([^"]+)"',
        html
    )
    detail["news"] = [
        {"title": n[0], "press": n[1], "url": n[2]}
        for n in news[:4]
    ]
 
    return detail
 
 
# ── 메인 크롤러 ───────────────────────────────────
def crawl(fetch_detail: bool = True) -> dict:
    result = {
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "apts": [],
        "errors": [],
    }
 
    # ① 목록 수집 — API 직접 호출
    log.info("=" * 50)
    log.info("부산 분양 목록 수집 시작 (API)")
    apts = fetch_all_apts_api()
    log.info("목록 수집 완료 — 총 %d개 단지", len(apts))
 
    if not apts:
        log.error("수집된 단지 없음 — 크롤링 실패")
        result["errors"].append({"phase": "list", "error": "수집된 단지 없음"})
        return result
 
    # ② 상세 페이지 — Selenium (관심도 상위 10개만)
    if fetch_detail:
        log.info("상세 페이지 수집 시작 (Selenium) — 상위 10개")
        driver = make_driver()
        try:
            top = sorted(apts, key=lambda a: a.get("alarmCount", 0), reverse=True)[:10]
            for apt in top:
                url = f"https://hogangnono.com/apt/{apt['hash']}"
                log.info("상세 크롤링: %s (%s)", apt["name"], apt["hash"])
                try:
                    driver.get(url)
                    time.sleep(4)
                    apt.update(parse_detail(driver.page_source))
                except Exception as e:
                    log.warning("상세 실패 [%s]: %s", apt["hash"], e)
                    result["errors"].append({"hash": apt["hash"], "error": str(e)})
        finally:
            driver.quit()
        log.info("상세 수집 완료")
 
    result["apts"] = apts
    return result
 
 
# ── 저장 ─────────────────────────────────────────
def save(data: dict):
    OUTPUT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log.info("저장 완료: %s (%d개 단지)", OUTPUT_FILE, len(data["apts"]))
 
 
# ── 실행 ─────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="호갱노노 부산 청약 크롤러")
    parser.add_argument(
        "--no-detail",
        action="store_true",
        help="상세 페이지 수집 스킵 (빠름, 약 10~20초)"
    )
    args = parser.parse_args()
 
    log.info("크롤링 시작")
    data = crawl(fetch_detail=not args.no_detail)
    save(data)
    log.info("완료 — %d개 단지 저장", len(data["apts"]))