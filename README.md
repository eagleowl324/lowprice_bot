# 🛒 lowprice_bot

네이버 쇼핑 검색 스킬 기반 물티슈 최저가 알림 및 카카오톡 자동 전송 봇입니다.

## 📌 주요 기능
1. **네이버 쇼핑 최저가 검색**: "베베앙 20개" 키워드를 최저가 순(`price_asc`)으로 조회
2. **광고 상품 필터링**: `is_ad`, `adType`, 상품명/판매처의 `[광고]` 표기를 정밀 제외하고 순수 상품만 선별
3. **TOP 3 상품 정보 출력**: 1~3위 상품의 상품명, 가격, 쇼핑몰, 리뷰수, 링크를 깔끔하게 출력
4. **목표 가격 판정**: 1위 가격이 20,000원 이하일 경우 특가 안내, 초과일 경우 유지 안내 출력
5. **카카오톡 '나에게 보내기' 알림**: 특가 발견 시 카카오톡 메시지 및 '구매하러 가기' 버튼 링크 자동 전송

## 🚀 실행 방법

### 1. 환경 설정
`.env` 파일에 카카오 인증 정보를 설정합니다.
```env
KAKAO_REST_API_KEY=your_kakao_rest_api_key
KAKAO_CLIENT_SECRET=your_kakao_client_secret
KAKAO_REFRESH_TOKEN=your_kakao_refresh_token
```

### 2. 봇 실행
```bash
# 기본 실행
python lowprice_bot.py

# 데모/테스트 모드 (가상 데이터 및 카카오톡 전송 시연)
python lowprice_bot.py --demo
```

### 3. 무결성 검증 테스트 실행
```bash
python test_lowprice_bot.py
```
