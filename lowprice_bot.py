"""
lowprice_bot.py - 네이버 쇼핑 검색 스킬 기반 물티슈 최저가 알림 봇

[요구사항 구현 내역]
1. 네이버 쇼핑 검색 스킬(GET /v1/naver-shopping/search)로 "베베앙 20개"를 최저가 순(price_asc)으로 검색
2. 최저가 순서로 상품 3개를 상품명, 가격, 쇼핑몰, 리뷰수, 링크와 함께 화면에 깔끔하게 출력
3. 반환된 광고 상품(is_ad, ad, [광고] 태그 등)은 엄격히 필터링하여 순수 상품만 선별
4. 1위 가격이 목표가(20,000원) 이하인지 확인 후 알림 문구 출력:
   - 목표가 이하: "[특가발견] 목표 가격 이하입니다!"
   - 목표가 초과: "[유지] 아직 목표 가격 보다 비싸요!"
5. 잘못된 값을 가져올 경우(HTTP 오류, JSON 파싱 실패, 필드 누락 등) 임의로 값을 지어내지 않고
   무엇이 잘못되었는지 정확하게 출력한 뒤 즉시 종료
"""

import sys
import os
import json
import re
import urllib.request
import urllib.parse
import urllib.error

# 설정값
KEYWORD = "베베앙 20개"
SORT_ORDER = "price_asc"
FETCH_LIMIT = 20           # 광고 필터링 후 3개 확보를 위해 넉넉하게 요청
TARGET_PRICE = 20000       # 목표가 (20,000원)
TOP_N = 3                  # 화면에 출력할 상품 개수

# 기본 스킬 프록시 엔드포인트 (환경변수로 재지정 가능)
DEFAULT_API_URL = "https://k-skill-proxy.nomadamas.org/v1/naver-shopping/search"
API_URL = os.environ.get("NAVER_SHOPPING_PROXY_URL", DEFAULT_API_URL)

# .env 파일 경로 (프로젝트 폴더 내 위치)
ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env_config() -> dict:
    """프로젝트 폴더의 .env 파일 또는 시스템 환경변수(GitHub Secrets 등)에서 카카오 인증 정보를 안전하게 읽어옵니다."""
    config = {}
    if os.path.exists(ENV_FILE_PATH):
        with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()

    # 시스템 환경변수(GitHub Actions secrets 등)에서 fallback 로드
    for key in ["KAKAO_REST_API_KEY", "KAKAO_CLIENT_SECRET", "KAKAO_REFRESH_TOKEN"]:
        if not config.get(key) and os.environ.get(key):
            config[key] = os.environ.get(key).strip()

    return config


def update_env_refresh_token(new_refresh_token: str):
    """카카오 서버에서 갱신된 리프레시 토큰이 반환된 경우 .env를 자동 업데이트합니다."""
    if not os.path.exists(ENV_FILE_PATH):
        return

    with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    found = False
    for line in lines:
        if line.strip().startswith("KAKAO_REFRESH_TOKEN="):
            new_lines.append(f"KAKAO_REFRESH_TOKEN={new_refresh_token}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"KAKAO_REFRESH_TOKEN={new_refresh_token}\n")

    with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def get_kakao_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """리프레시 토큰을 이용해 카카오 API 호출용 신규 액세스 토큰을 발급받습니다."""
    url = "https://kauth.kakao.com/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            access_token = res_json.get("access_token")
            if not access_token:
                raise RuntimeError(f"토큰 갱신 응답에 access_token이 없습니다: {body}")

            # 리프레시 토큰이 함께 재발급된 경우 .env 자동 갱신
            if res_json.get("refresh_token"):
                update_env_refresh_token(res_json["refresh_token"])

            return access_token
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"카카오 토큰 갱신 실패 [HTTP {e.code}]: {err_body}") from e
    except Exception as e:
        raise RuntimeError(f"카카오 토큰 갱신 네트워크 오류: {e}") from e


def send_kakao_memo(product: dict) -> bool:
    """
    1위 상품 정보를 카카오톡 '나에게 보내기'로 전송합니다.
    실패 시 보낸 척하지 않고 구체적인 실패 사유를 상세히 출력합니다.
    """
    # 1. .env 파일에서 인증 정보 로드 (하드코딩 방지)
    env_config = load_env_config()
    client_id = env_config.get("KAKAO_REST_API_KEY")
    client_secret = env_config.get("KAKAO_CLIENT_SECRET")
    refresh_token = env_config.get("KAKAO_REFRESH_TOKEN")

    if not client_id or not refresh_token:
        print("\n❌ [카카오톡 전송 실패 - 인증 정보 누락]")
        print("  • 원인: .env 파일에 KAKAO_REST_API_KEY 또는 KAKAO_REFRESH_TOKEN이 설정되어 있지 않습니다.")
        print("  • 조치: 보낸 척하지 않고 알림 전송을 중단합니다.")
        return False

    # 2. 액세스 토큰 획득
    try:
        access_token = get_kakao_access_token(client_id, client_secret, refresh_token)
    except Exception as e:
        print("\n❌ [카카오톡 전송 실패 - 액세스 토큰 발급 오류]")
        print(f"  • 원인: {e}")
        print("  • 조치: 보낸 척하지 않고 알림 전송을 중단합니다.")
        return False

    # 3. 템플릿 구성 (상품명, 가격, 쇼핑몰, 리뷰수, '구매하러 가기' 버튼 링크)
    title = product.get("title", "상품명 없음")
    price = product.get("price", 0)
    mall_name = product.get("mall_name", "판매처 정보 없음")
    review_count = product.get("review_count", 0)
    link = product.get("link") or "https://shopping.naver.com"

    message_text = (
        f"🎉 [특가발견] 베베앙 물티슈 최저가 알림!\n\n"
        f"• 상품명: {title}\n"
        f"• 가  격: {price:,}원\n"
        f"• 쇼핑몰: {mall_name}\n"
        f"• 리뷰수: {review_count:,}개"
    )

    template_object = {
        "object_type": "text",
        "text": message_text,
        "link": {
            "web_url": link,
            "mobile_web_url": link,
        },
        "button_title": "구매하러 가기",
    }

    memo_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    memo_data = urllib.parse.urlencode({
        "template_object": json.dumps(template_object, ensure_ascii=False)
    }).encode("utf-8")

    memo_req = urllib.request.Request(
        memo_url,
        data=memo_data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        },
    )

    # 4. 카카오톡 메시지 전송 및 엄격한 성공/실패 판정
    try:
        with urllib.request.urlopen(memo_req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            res_json = json.loads(resp_body)
            if res_json.get("result_code") == 0:
                print("\n💬 [카카오톡 알림 전송 완료]")
                print("  • '나에게 보내기' 메시지가 성공적으로 전송되었습니다!")
                print(f"  • 전송 내용: {title} ({price:,}원 / {mall_name})")
                return True
            else:
                print(f"\n❌ [카카오톡 전송 실패 - 비정상 결과 코드]")
                print(f"  • 응답: {resp_body}")
                print("  • 조치: 보낸 척하지 않고 실패를 안내합니다.")
                return False
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="replace")
        print(f"\n❌ [카카오톡 전송 실패 - HTTP {he.code} {he.reason}]")
        print(f"  • 상세 내용: {err_body}")
        print("  • 조치: 보낸 척하지 않고 실패를 안내합니다.")
        return False
    except Exception as ex:
        print(f"\n❌ [카카오톡 전송 실패 - 전송 중 네트워크/시스템 오류]")
        print(f"  • 상세 내용: {ex}")
        print("  • 조치: 보낸 척하지 않고 실패를 안내합니다.")
        return False


def clean_html(text: str) -> str:
    """상품명 등에 포함된 HTML 태그(<b> 등)를 제거합니다."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_price(price_val) -> int:
    """가격 값을 정수로 안전하게 변환합니다."""
    if isinstance(price_val, (int, float)):
        return int(price_val)
    if isinstance(price_val, str):
        clean_num = re.sub(r"[^\d]", "", price_val)
        if clean_num:
            return int(clean_num)
    raise ValueError(f"유효한 가격 형태가 아닙니다: {price_val}")


def parse_review_count(review_val) -> int:
    """리뷰 수 값을 정수로 안전하게 변환합니다."""
    if not review_val:
        return 0
    if isinstance(review_val, (int, float)):
        return int(review_val)
    if isinstance(review_val, str):
        clean_num = re.sub(r"[^\d]", "", review_val)
        return int(clean_num) if clean_num else 0
    return 0


def is_advertisement(item: dict) -> bool:
    """광고 상품 여부를 정밀 판별합니다."""
    # 1. API 명세의 광고 필드 플래그 확인
    if item.get("is_ad") is True or item.get("ad") is True or item.get("isAd") is True:
        return True
    if item.get("adType") or item.get("ad_type"):
        return True

    # 2. 제목이나 판매처 내 광고 표기 확인
    title = str(item.get("title", ""))
    mall_name = str(item.get("mall_name", "") or item.get("mallName", ""))
    if "[광고]" in title or "(광고)" in title:
        return True
    if "[광고]" in mall_name:
        return True

    return False


def fetch_naver_shopping(keyword: str, sort: str, limit: int) -> dict:
    """
    네이버 쇼핑 검색 스킬 엔드포인트를 호출합니다.
    오류 발생 시 임의의 데이터를 생성하지 않고 예외를 발생시킵니다.
    """
    params = {
        "q": keyword,
        "sort": sort,
        "limit": str(limit),
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "lowprice-bot/1.0 (Python urllib)",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.getcode()
            if status_code != 200:
                raise RuntimeError(
                    f"서버가 정상 코드(200)가 아닌 HTTP {status_code} 상태를 반환했습니다."
                )

            body = response.read().decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError as jde:
                raise RuntimeError(
                    f"응답 본문을 JSON으로 파싱할 수 없습니다. 원문: {body[:200]}"
                ) from jde

            return data

    except urllib.error.HTTPError as he:
        # HTTP 에러 (404, 500, 403 등)
        error_detail = ""
        try:
            error_body = he.read().decode("utf-8", errors="replace")
            error_json = json.loads(error_body)
            error_detail = f"상세 내용: {error_json.get('message', error_body)}"
        except Exception:
            error_detail = f"상세 내용: {he.reason}"

        raise RuntimeError(
            f"네이버 쇼핑 스킬 API 호출 실패 [HTTP {he.code} {he.reason}]\n"
            f"요청 URL: {url}\n"
            f"{error_detail}\n"
            f"참고: 네이버 검색 API 종료 또는 프록시 엔드포인트 변경으로 인해 요청이 거부되었을 수 있습니다."
        ) from he

    except urllib.error.URLError as ue:
        # 네트워크/DNS 오류 등
        raise RuntimeError(
            f"네트워크 연결 오류로 인해 서버에 접속할 수 없습니다: {ue.reason}\n"
            f"요청 URL: {url}"
        ) from ue


def run_bot(custom_data=None, exit_on_error=True, send_notification=True):
    print("=" * 65)
    print(" 🛒  [lowprice_bot] 물티슈 최저가 알림 봇 시작")
    print(f" 🔍  검색 키워드: '{KEYWORD}' | 정렬: {SORT_ORDER} (최저가순)")
    print(f" 🎯  목표 가격: {TARGET_PRICE:,}원 이하")
    print(f" 🌐  엔드포인트: {API_URL}")
    print("=" * 65)

    def handle_error(title: str, msg: str):
        print(f"\n❌ [{title}]")
        print("잘못된 값이나 오류가 발생하여 임의의 값을 지어내지 않고 처리를 중단합니다.")
        print("-" * 65)
        print(msg)
        print("-" * 65)
        print("봇을 종료합니다 (종료 코드: 1).")
        if exit_on_error:
            sys.exit(1)
        return False

    # 1. 네이버 쇼핑 검색 스킬로 데이터 수집
    if custom_data is not None:
        raw_data = custom_data
    elif "--demo" in sys.argv or "--mock" in sys.argv:
        print("\n🧪 [데모/테스트 모드 실행 - 광고 필터링 및 정상 출력 시연]")
        raw_data = {
            "items": [
                {
                    "title": "[광고] 베베앙 물티슈 70매 10팩 타임특가",
                    "price": 8900,
                    "mall_name": "광고대행스토어",
                    "review_count": 12,
                    "is_ad": True,
                    "url": "https://shopping.naver.com/ad_sample",
                },
                {
                    "title": "베베앙 물티슈 캡형 75평량 70매 20팩",
                    "price": 16400,
                    "mall_name": "베베앙 공식 브랜드스토어",
                    "review_count": 18520,
                    "is_ad": False,
                    "url": "https://shopping.naver.com/catalog/sample1",
                },
                {
                    "title": "베베앙 프리미엄 골드 82평량 70매 20팩",
                    "price": 17900,
                    "mall_name": "11번가",
                    "review_count": 9430,
                    "is_ad": False,
                    "url": "https://shopping.naver.com/catalog/sample2",
                },
                {
                    "title": "(광고) 베베앙 물티슈 파워딜",
                    "price": 15000,
                    "mall_name": "오픈마켓 [광고]",
                    "review_count": 45,
                    "is_ad": False,
                    "url": "https://shopping.naver.com/ad_sample2",
                },
                {
                    "title": "베베앙 시그니처 캡형 100매 20팩",
                    "price": 26500,
                    "mall_name": "G마켓",
                    "review_count": 6210,
                    "is_ad": False,
                    "url": "https://shopping.naver.com/catalog/sample3",
                },
                {
                    "title": "베베앙 오리지널 플러스 100매 20팩",
                    "price": 28900,
                    "mall_name": "옥션",
                    "review_count": 3150,
                    "is_ad": False,
                    "url": "https://shopping.naver.com/catalog/sample4",
                },
            ]
        }
    else:
        try:
            raw_data = fetch_naver_shopping(KEYWORD, SORT_ORDER, FETCH_LIMIT)
        except Exception as e:
            return handle_error("오류 발생 - 스킬 호출 실패", str(e))

    # 2. 반환 데이터 무결성 검증
    if not isinstance(raw_data, dict):
        return handle_error("오류 발생 - 데이터 형식 불일치", f"응답 데이터가 JSON 객체 형태가 아닙니다: {type(raw_data)}")

    items = raw_data.get("items")
    if items is None or not isinstance(items, list):
        keys = list(raw_data.keys()) if isinstance(raw_data, dict) else []
        return handle_error("오류 발생 - 상품 목록 부재", f"응답 내에 'items' 목록이 존재하지 않거나 올바르지 않습니다. (응답 키: {keys})")

    if len(items) == 0:
        return handle_error("오류 발생 - 검색 결과 0건", f"'{KEYWORD}'에 대한 검색 결과가 0건입니다.")

    # 3. 광고 상품 필터링 및 데이터 정제
    filtered_items = []
    ad_count = 0

    for item in items:
        if is_advertisement(item):
            ad_count += 1
            continue

        title = clean_html(item.get("title", ""))
        mall_name = item.get("mall_name") or item.get("mallName") or "판매처 정보 없음"
        link = item.get("url") or item.get("link") or ""

        # 필수 필드 유효성 검사 (가격 검증)
        price_raw = item.get("price") or item.get("lprice")
        if price_raw is None:
            continue

        try:
            price = parse_price(price_raw)
        except ValueError:
            continue

        if price <= 0:
            continue

        review_count = parse_review_count(
            item.get("review_count") or item.get("reviewCount")
        )

        filtered_items.append(
            {
                "title": title,
                "price": price,
                "mall_name": mall_name,
                "review_count": review_count,
                "link": link,
            }
        )

    print(f"\n📊 총 수신 상품: {len(items)}개 | 광고 제외: {ad_count}개 | 유효 상품: {len(filtered_items)}개")

    if not filtered_items:
        return handle_error("오류 발생 - 유효 상품 없음", "수신된 상품이 모두 광고이거나 올바른 가격 정보가 없습니다.")

    # 가격 오름차순 정렬 (혹시 모를 서버 정렬 불일치 대비 안전장치)
    filtered_items.sort(key=lambda x: x["price"])

    # 상위 TOP_N(3개) 추출
    top_items = filtered_items[:TOP_N]

    # 4. 화면에 보기 좋게 출력
    print("\n" + "=" * 65)
    print(f" 🏆  [베베앙 20개 최저가 순위 TOP {len(top_items)}]")
    print("=" * 65)

    for rank, prod in enumerate(top_items, 1):
        print(f"\n[{rank}위] {prod['title']}")
        print(f"  • 가  격 : {prod['price']:,}원")
        print(f"  • 판매처 : {prod['mall_name']}")
        print(f"  • 리뷰수 : {prod['review_count']:,}개")
        print(f"  • 링크   : {prod['link']}")
        print("  " + "-" * 60)

    # 5. 1위 가격과 목표가(20,000원) 비교 및 알림 문구 출력
    lowest_product = top_items[0]
    lowest_price = lowest_product["price"]

    print("\n" + "=" * 65)
    print(" 📢  [목표 가격 달성 여부]")
    print(f"  • 1위 최저가: {lowest_price:,}원 (목표가: {TARGET_PRICE:,}원)")

    if lowest_price <= TARGET_PRICE:
        status_msg = "[특가발견] 목표 가격 이하입니다!"
        print(f"  • 판    정 : {status_msg}")
        print("=" * 65)
        # 1. 1위 가격이 목표가 이하일 때만 카카오톡 알림 전송
        if send_notification:
            send_kakao_memo(lowest_product)
    else:
        status_msg = "[유지] 아직 목표 가격 보다 비싸요!"
        print(f"  • 판    정 : {status_msg}")
        print("=" * 65)
        # 목표가 초과 시에는 카카오톡 메시지를 보내지 않고 화면에만 안내
        print(f"\nℹ️ [알림 생략] 1위 가격({lowest_price:,}원)이 목표가({TARGET_PRICE:,}원)를 초과하므로 카카오톡 메시지를 전송하지 않습니다.")
    return True


if __name__ == "__main__":
    run_bot()
