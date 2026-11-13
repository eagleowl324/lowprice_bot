"""
test_lowprice_bot.py - lowprice_bot.py 단위 검증 및 무결성 테스트 스크립트

[검사 항목 4가지]
1. 20000원 이하 일 때 특가 메시지가 출력되는가?
2. 20000원 초과 일 때 유지 메시지가 출력되는가?
3. 광고 상품이 섞여 있을 때 걸러낼 수 있는가?
4. 값을 가져오지 못했을 경우 멈추지 않고 오류를 알려주는가?

[검사 원칙]
- 실제 네이버/외부 네트워크에 일절 요청하지 않고 오직 가상(Mock) 데이터만 사용
- 각 항목별 PASS / FAIL 상태 및 상세 검증 결과 목록 출력
- 검사 항목을 임의로 느슨하게 완화하거나 지우지 않는 엄격한 검증
"""

import sys
import io
import contextlib
from unittest.mock import patch
import lowprice_bot


def capture_run(custom_data=None, patch_fetch_exception=None, exit_on_error=False):
    """
    lowprice_bot.run_bot()을 실행하고 표준 출력(stdout) 및 표준 에러(stderr)를 캡처합니다.
    sys.exit() 호출 시 SystemExit 예외를 잡아 정상적으로 출력을 수집합니다.
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 0
    returned_val = None

    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        try:
            if patch_fetch_exception is not None:
                with patch.object(
                    lowprice_bot, "fetch_naver_shopping", side_effect=patch_fetch_exception
                ):
                    returned_val = lowprice_bot.run_bot(
                        custom_data=None, exit_on_error=exit_on_error
                    )
            else:
                returned_val = lowprice_bot.run_bot(
                    custom_data=custom_data, exit_on_error=exit_on_error
                )
        except SystemExit as se:
            exit_code = se.code

    output = stdout_buf.getvalue() + "\n" + stderr_buf.getvalue()
    return output, exit_code, returned_val


def test_1_under_20000():
    """1. 20000원 이하 일 때 특가 메시지가 출력되는가?"""
    # 1위 최저가가 16,400원(20,000원 이하)인 가상 데이터
    mock_data = {
        "items": [
            {
                "title": "베베앙 물티슈 캡형 75평량 70매 20팩",
                "price": 16400,
                "mall_name": "베베앙 공식몰",
                "review_count": 12500,
                "is_ad": False,
                "url": "https://shopping.naver.com/test1",
            },
            {
                "title": "베베앙 프리미엄 골드 82평량 70매 20팩",
                "price": 17900,
                "mall_name": "11번가",
                "review_count": 8900,
                "is_ad": False,
                "url": "https://shopping.naver.com/test2",
            },
            {
                "title": "베베앙 시그니처 100매 20팩",
                "price": 26500,
                "mall_name": "G마켓",
                "review_count": 5200,
                "is_ad": False,
                "url": "https://shopping.naver.com/test3",
            },
        ]
    }

    output, exit_code, _ = capture_run(custom_data=mock_data)

    target_msg = "[특가발견] 목표 가격 이하입니다!"
    wrong_msg = "[유지] 아직 목표 가격 보다 비싸요!"

    has_target = target_msg in output
    has_no_wrong = wrong_msg not in output
    has_correct_price = "16,400원" in output

    passed = has_target and has_no_wrong and has_correct_price

    detail = (
        f"1위 최저가 16,400원 확인 -> '{target_msg}' 출력 검증 성공"
        if passed
        else f"특가 메시지 누락 또는 잘못된 출력 (출력 여부: has_target={has_target}, has_no_wrong={has_no_wrong})"
    )

    return passed, detail


def test_2_over_20000():
    """2. 20000원 초과 일 때 유지 메시지가 출력되는가?"""
    # 최저가가 21,500원(20,000원 초과)인 가상 데이터
    mock_data = {
        "items": [
            {
                "title": "베베앙 시그니처 캡형 100매 20팩",
                "price": 21500,
                "mall_name": "베베앙 본사몰",
                "review_count": 4500,
                "is_ad": False,
                "url": "https://shopping.naver.com/test_over1",
            },
            {
                "title": "베베앙 오리지널 플러스 100매 20팩",
                "price": 27900,
                "mall_name": "옥션",
                "review_count": 3100,
                "is_ad": False,
                "url": "https://shopping.naver.com/test_over2",
            },
            {
                "title": "베베앙 프리미엄 100매 20팩",
                "price": 31000,
                "mall_name": "롯데온",
                "review_count": 1200,
                "is_ad": False,
                "url": "https://shopping.naver.com/test_over3",
            },
        ]
    }

    output, exit_code, _ = capture_run(custom_data=mock_data)

    target_msg = "[유지] 아직 목표 가격 보다 비싸요!"
    wrong_msg = "[특가발견] 목표 가격 이하입니다!"

    has_target = target_msg in output
    has_no_wrong = wrong_msg not in output
    has_correct_price = "21,500원" in output

    passed = has_target and has_no_wrong and has_correct_price

    detail = (
        f"1위 최저가 21,500원 확인 -> '{target_msg}' 출력 검증 성공"
        if passed
        else f"유지 메시지 누락 또는 잘못된 출력 (출력 여부: has_target={has_target}, has_no_wrong={has_no_wrong})"
    )

    return passed, detail


def test_3_filter_advertisements():
    """3. 광고 상품이 섞여 있을 때 걸러낼 수 있는가?"""
    # 가격이 더 저렴한 광고 상품 4개와 일반 상품 4개가 혼합된 가상 데이터
    # 광고 상품이 걸러지지 않으면 광고 상품(5,000원)이 1위로 선정되는 엄격한 트랩 구성
    mock_data = {
        "items": [
            {
                "title": "[광고] 베베앙 물티슈 50매 10팩 초특가",
                "price": 5000,
                "mall_name": "광고대행스토어",
                "review_count": 10,
                "is_ad": True,  # is_ad 플래그
                "url": "https://shopping.naver.com/ad1",
            },
            {
                "title": "베베앙 프리미엄 파워특가",
                "price": 6000,
                "mall_name": "오픈마켓 [광고]",  # 쇼핑몰명 내 [광고]
                "review_count": 25,
                "is_ad": False,
                "url": "https://shopping.naver.com/ad2",
            },
            {
                "title": "(광고) 베베앙 물티슈 번들팩",  # 제목 내 (광고)
                "price": 7000,
                "mall_name": "일반스토어",
                "review_count": 30,
                "is_ad": False,
                "url": "https://shopping.naver.com/ad3",
            },
            {
                "title": "베베앙 스폰서 기획 상품",
                "price": 8000,
                "mall_name": "제휴몰",
                "review_count": 50,
                "adType": "SPONSORED",  # adType 플래그
                "url": "https://shopping.naver.com/ad4",
            },
            # 순수 일반 상품군
            {
                "title": "베베앙 물티슈 캡형 75평량 70매 20팩",
                "price": 16400,
                "mall_name": "베베앙 공식 브랜드스토어",
                "review_count": 18520,
                "is_ad": False,
                "url": "https://shopping.naver.com/real1",
            },
            {
                "title": "베베앙 프리미엄 골드 82평량 70매 20팩",
                "price": 17900,
                "mall_name": "11번가",
                "review_count": 9430,
                "is_ad": False,
                "url": "https://shopping.naver.com/real2",
            },
            {
                "title": "베베앙 시그니처 캡형 100매 20팩",
                "price": 26500,
                "mall_name": "G마켓",
                "review_count": 6210,
                "is_ad": False,
                "url": "https://shopping.naver.com/real3",
            },
            {
                "title": "베베앙 오리지널 플러스 100매 20팩",
                "price": 28900,
                "mall_name": "옥션",
                "review_count": 3150,
                "is_ad": False,
                "url": "https://shopping.naver.com/real4",
            },
        ]
    }

    output, exit_code, _ = capture_run(custom_data=mock_data)

    # 검증 1: 1위 최저가는 광고 가격(5,000원~8,000원)이 아닌 순수 상품 최저가(16,400원)이어야 함
    has_real_lowest = "16,400원" in output and "5,000원" not in output

    # 검증 2: TOP 3 순위권 내에 광고성 상품명이 포함되지 않아야 함
    ad_leaked = any(
        ad_text in output
        for ad_text in [
            "[광고] 베베앙",
            "오픈마켓 [광고]",
            "(광고) 베베앙",
            "베베앙 스폰서 기획 상품",
        ]
    )

    # 검증 3: 순수 일반 상품 상위 3개가 순위권에 포함되어 있어야 함
    has_real_top3 = (
        "베베앙 물티슈 캡형 75평량 70매 20팩" in output
        and "베베앙 프리미엄 골드 82평량 70매 20팩" in output
        and "베베앙 시그니처 캡형 100매 20팩" in output
    )

    # 검증 4: 광고 제외 카운트 정상 집계 확인
    has_ad_count = "광고 제외: 4개" in output

    passed = has_real_lowest and (not ad_leaked) and has_real_top3 and has_ad_count

    detail = (
        "광고 4개([광고], (광고), is_ad, adType) 전량 필터링 성공, 순수 상품 3개 정상 선별 확인 (1위 최저가: 16,400원)"
        if passed
        else f"광고 필터링 실패 (has_real_lowest={has_real_lowest}, ad_leaked={ad_leaked}, has_real_top3={has_real_top3}, has_ad_count={has_ad_count})"
    )

    return passed, detail


def test_4_error_reporting_when_fetch_fails():
    """4. 값을 가져오지 못했을 경우 멈추지 않고 오류를 알려주는가?"""
    # 시나리오 A: HTTP 404 / API 호출 실패 예외 발생 시
    api_error = RuntimeError(
        "네이버 쇼핑 스킬 API 호출 실패 [HTTP 404 Not Found]\n"
        "상세 내용: Route GET:/v1/naver-shopping/search not found"
    )
    output_a, exit_code_a, _ = capture_run(
        patch_fetch_exception=api_error, exit_on_error=True
    )

    has_error_mark_a = "❌ [오류 발생" in output_a or "오류 발생" in output_a
    has_error_detail_a = "404 Not Found" in output_a or "호출 실패" in output_a
    has_no_hallucination_a = (
        "[1위]" not in output_a and "[특가발견]" not in output_a and "[유지]" not in output_a
    )
    handled_cleanly_a = exit_code_a != 0  # 에러 종료 코드로 정상 종료됨

    # 시나리오 B: 응답이 빈 데이터이거나 items 목록이 비어있는 경우
    empty_data = {"items": []}
    output_b, exit_code_b, _ = capture_run(
        custom_data=empty_data, exit_on_error=True
    )

    has_error_mark_b = "❌ [오류 발생" in output_b or "오류 발생" in output_b
    has_error_detail_b = "검색 결과 0건" in output_b or "0건" in output_b
    has_no_hallucination_b = (
        "[1위]" not in output_b and "[특가발견]" not in output_b and "[유지]" not in output_b
    )
    handled_cleanly_b = exit_code_b != 0

    passed = (
        has_error_mark_a
        and has_error_detail_a
        and has_no_hallucination_a
        and handled_cleanly_a
        and has_error_mark_b
        and has_error_detail_b
        and has_no_hallucination_b
        and handled_cleanly_b
    )

    detail = (
        "API 404 실패 및 빈 데이터 수신 시, 가짜 데이터를 날조하지 않고 정확한 오류 원인을 출력하며 정상 중단됨 확인"
        if passed
        else f"오류 알림 실패 (A통과={has_error_mark_a and has_error_detail_a}, B통과={has_error_mark_b and has_error_detail_b})"
    )

    return passed, detail


def run_all_tests():
    """모든 검사 항목을 순차적으로 실행하고 목록 형태로 결과를 출력합니다."""
    print("=" * 70)
    print(" 🧪  lowprice_bot.py 가상 데이터 기반 무결성 검증 시작")
    print(" 📌  외부 네트워크 요청 차단 (Pure Mock 데이터 활용)")
    print("=" * 70)

    test_cases = [
        ("1. 20000원 이하 일 때 특가 메시지가 출력되는가?", test_1_under_20000),
        ("2. 20000원 초과 일 때 유지 메시지가 출력되는가?", test_2_over_20000),
        ("3. 광고 상품이 섞여 있을 때 걸러낼 수 있는가?", test_3_filter_advertisements),
        ("4. 값을 가져오지 못했을 경우 멈추지 않고 오류를 알려주는가?", test_4_error_reporting_when_fetch_fails),
    ]

    all_passed = True
    results = []

    for idx, (title, test_fn) in enumerate(test_cases, 1):
        try:
            passed, detail = test_fn()
        except Exception as e:
            passed = False
            detail = f"테스트 실행 도중 예기치 못한 예외 발생: {type(e).__name__}: {e}"

        status_str = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False

        results.append((title, status_str, detail))

    print("\n[검사 결과 목록]")
    print("-" * 70)
    for title, status_str, detail in results:
        status_label = f"[{status_str}]"
        print(f" {status_label:<8} {title}")
        print(f"          ↳ {detail}\n")
    print("-" * 70)

    pass_count = sum(1 for _, s, _ in results if s == "PASS")
    total_count = len(results)

    print("=" * 70)
    if all_passed:
        print(f" 🏁 최종 판정: ALL PASS ({pass_count}/{total_count} 항목 통과)")
        print("    lowprice_bot.py가 모든 검사 조건을 완벽히 충족합니다.")
    else:
        print(f" ⚠️ 최종 판정: FAIL 발생 ({pass_count}/{total_count} 항목 통과)")
        print("    통과하지 못한 항목에 대해 lowprice_bot.py 수정이 필요합니다.")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
