"""유니클로 한국 공식 사이트의 상품 검색 API에서 세일 정보를 모아 docs/data.json 으로 저장한다.

표준 라이브러리만 사용하므로 별도 설치 없이 `python collector/collect.py` 로 실행할 수 있다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://www.uniqlo.com/kr/api/commerce/v5/ko/products"
PRODUCT_URL = "https://www.uniqlo.com/kr/ko/products/{product_id}/{price_group}"
# 브라우저가 아닌 User-Agent 로 요청하면 API 가 응답하지 않는다.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
PAGE_SIZE = 100  # API 가 허용하는 최대값
MAX_PAGES = 20
KST = timezone(timedelta(hours=9))

# 기간한정가격 상품이 이 수 이상이면 감사제 같은 대형 세일로 본다. 평소에는 수십 개 수준이다.
BIG_SALE_THRESHOLD = 80
HISTORY_LIMIT = 100
DISCOUNT_PRODUCT_LIMIT = 60


def fetch(params: dict[str, str | int]) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.load(response)
            return body["result"]
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def fetch_flagged(flag_code: str) -> tuple[list[dict], list[dict]]:
    """flag_code 가 붙은 상품 전체와 플래그별 상품 수 집계를 돌려준다."""
    items: list[dict] = []
    aggregations: list[dict] = []
    for page in range(MAX_PAGES):
        result = fetch({"flagCodes": flag_code, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
        if page == 0:
            aggregations = result.get("aggregations", {}).get("flags", [])
        items.extend(result.get("items", []))
        if len(items) >= result["pagination"]["total"] or not result.get("items"):
            break
    return items, aggregations


def price_flag(item: dict, flag_code: str) -> dict | None:
    for flag in item.get("representative", {}).get("flags", {}).get("priceFlags", []):
        if flag.get("code") == flag_code:
            return flag
    return None


def to_product(item: dict) -> dict:
    color = item.get("representativeColorDisplayCode", "")
    main_images = item.get("images", {}).get("main", {})
    image = (main_images.get(color) or next(iter(main_images.values()), {})).get("image", "")
    rating = item.get("rating") or {}
    return {
        "id": item["productId"],
        "name": item.get("name", ""),
        "gender": item.get("genderName", ""),
        "price": item.get("prices", {}).get("promo", {}).get("value")
        or item.get("prices", {}).get("base", {}).get("value"),
        "image": image,
        "url": PRODUCT_URL.format(product_id=item["productId"], price_group=item.get("priceGroup", "00")),
        "rating": rating.get("average"),
        "reviews": rating.get("count", 0),
    }


def kst_date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, KST).strftime("%Y/%m/%d")


def group_periods(items: list[dict], flag_code: str) -> list[dict]:
    """같은 시작·종료 시각을 가진 상품을 하나의 세일 회차로 묶는다."""
    periods: dict[str, dict] = {}
    for item in items:
        flag = price_flag(item, flag_code)
        if not flag:
            continue
        effective = flag.get("effectiveTime", {})
        start, end = effective.get("start", 0), effective.get("end", 0)
        key = f"{flag_code}:{start}:{end}"
        if key not in periods:
            # 사이트에 표시되는 날짜 문구를 우선 쓴다. 종료 시각은 마지막 날 다음 날 새벽이라 그대로 바꾸면 하루 어긋난다.
            words = flag.get("nameWording", {}).get("substitutions", {})
            periods[key] = {
                "key": key,
                "label": words.get("flagName") or flag.get("name", flag_code),
                "startDate": words.get("startDate") or (kst_date(start) if start else ""),
                "endDate": words.get("date") or (kst_date(end) if end else ""),
                "start": start,
                "end": end,
                "products": [],
            }
        periods[key]["products"].append(to_product(item))
    result = sorted(periods.values(), key=lambda p: (p["end"], -len(p["products"])))
    for period in result:
        period["count"] = len(period["products"])
    return result


def merge_history(previous: dict, periods: list[dict], now: str) -> list[dict]:
    history = {entry["key"]: entry for entry in previous.get("history", [])}
    for period in periods:
        entry = history.setdefault(
            period["key"],
            {
                "key": period["key"],
                "label": period["label"],
                "startDate": period["startDate"],
                "endDate": period["endDate"],
                "start": period["start"],
                "end": period["end"],
                "firstSeen": now,
                "maxCount": 0,
            },
        )
        entry["maxCount"] = max(entry["maxCount"], period["count"])
        entry["lastSeen"] = now
    return sorted(history.values(), key=lambda e: e["start"], reverse=True)[:HISTORY_LIMIT]


def collect(previous: dict) -> dict:
    now = datetime.now(KST).isoformat(timespec="seconds")

    limited_items, flag_counts = fetch_flagged("limitedOffer")
    periods = group_periods(limited_items, "limitedOffer")

    discount_items, _ = fetch_flagged("discount")
    discount_products = []
    for item in discount_items:
        flag = price_flag(item, "discount") or {}
        product = to_product(item)
        product["since"] = flag.get("nameWording", {}).get("substitutions", {}).get("startDate", "")
        product["sinceTs"] = flag.get("effectiveTime", {}).get("start", 0)
        discount_products.append(product)
    discount_products.sort(key=lambda p: p["sinceTs"], reverse=True)

    limited_count = len(limited_items)
    return {
        "updatedAt": now,
        "bigSaleThreshold": BIG_SALE_THRESHOLD,
        "status": {
            "limitedOfferCount": limited_count,
            "discountCount": len(discount_items),
            "bigSale": limited_count >= BIG_SALE_THRESHOLD,
        },
        "flagCounts": [
            {"code": f["code"], "name": f["name"], "count": f.get("docCount", 0)} for f in flag_counts
        ],
        "periods": periods,
        "discount": discount_products[:DISCOUNT_PRODUCT_LIMIT],
        "history": merge_history(previous, periods, now),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("docs/data.json"))
    args = parser.parse_args()

    previous = {}
    if args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8"))

    data = collect(previous)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    status = data["status"]
    print(
        f"기간한정 {status['limitedOfferCount']}개 ({len(data['periods'])}회차), "
        f"가격인하 {status['discountCount']}개, 대형세일={status['bigSale']} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
