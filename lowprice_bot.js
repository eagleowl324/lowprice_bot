/**
 * lowprice_bot.js - 네이버 쇼핑 검색 스킬 기반 물티슈 최저가 알림 봇 (Node.js 버전)
 *
 * [요구사항 구현 내역]
 * 1. 네이버 쇼핑 검색 스킬(GET /v1/naver-shopping/search)로 "베베앙 20개"를 최저가 순(price_asc)으로 검색
 * 2. 최저가 순서로 상품 3개를 상품명, 가격, 쇼핑몰, 리뷰수, 링크와 함께 화면에 깔끔하게 출력
 * 3. 반환된 광고 상품(is_ad, ad, [광고] 태그 등)은 엄격히 필터링하여 순수 상품만 선별
 * 4. 1위 가격이 목표가(20,000원) 이하인지 확인 후 알림 문구 출력:
 *    - 목표가 이하: "[특가발견] 목표 가격 이하입니다!"
 *    - 목표가 초과: "[유지] 아직 목표 가격 보다 비싸요!"
 * 5. 잘못된 값을 가져올 경우(HTTP 오류, JSON 파싱 실패, 필드 누락 등) 임의로 값을 지어내지 않고
 *    무엇이 잘못되었는지 정확하게 출력한 뒤 즉시 종료 (exit code 1)
 */

const KEYWORD = "베베앙 20개";
const SORT_ORDER = "price_asc";
const FETCH_LIMIT = 20; // 광고 필터링 후 3개 확보를 위해 넉넉하게 요청
const TARGET_PRICE = 20000; // 목표가 (20,000원)
const TOP_N = 3;

// 기본 스킬 프록시 엔드포인트 (환경변수로 오버라이드 가능)
const DEFAULT_API_URL = "https://k-skill-proxy.nomadamas.org/v1/naver-shopping/search";
const API_URL = process.env.NAVER_SHOPPING_PROXY_URL || DEFAULT_API_URL;

function cleanHtml(text) {
  if (!text) return "";
  return String(text).replace(/<[^>]+>/g, "").trim();
}

function parsePrice(val) {
  if (typeof val === "number") return Math.floor(val);
  if (typeof val === "string") {
    const cleaned = val.replace(/[^\d]/g, "");
    if (cleaned) return parseInt(cleaned, 10);
  }
  throw new Error(`유효한 가격 형태가 아닙니다: ${val}`);
}

function parseReviewCount(val) {
  if (!val) return 0;
  if (typeof val === "number") return Math.floor(val);
  if (typeof val === "string") {
    const cleaned = val.replace(/[^\d]/g, "");
    return cleaned ? parseInt(cleaned, 10) : 0;
  }
  return 0;
}

function isAdvertisement(item) {
  if (item.is_ad === true || item.ad === true || item.isAd === true) return true;
  if (item.adType || item.ad_type) return true;

  const title = String(item.title || "");
  const mall = String(item.mall_name || item.mallName || "");
  if (title.includes("[광고]") || title.includes("(광고)")) return true;
  if (mall.includes("[광고]")) return true;

  return false;
}

async function fetchNaverShopping(keyword, sort, limit) {
  const url = new URL(API_URL);
  url.searchParams.set("q", keyword);
  url.searchParams.set("sort", sort);
  url.searchParams.set("limit", String(limit));

  let response;
  try {
    response = await fetch(url.toString(), {
      method: "GET",
      headers: {
        "User-Agent": "lowprice-bot/1.0 (Node.js fetch)",
        "Accept": "application/json",
      },
      signal: AbortSignal.timeout(10000),
    });
  } catch (err) {
    throw new Error(
      `네트워크 연결 오류로 인해 서버에 접속할 수 없습니다: ${err.message}\n요청 URL: ${url.toString()}`
    );
  }

  if (!response.ok) {
    let errorDetail = "";
    try {
      const errJson = await response.json();
      errorDetail = `상세 내용: ${errJson.message || JSON.stringify(errJson)}`;
    } catch {
      try {
        const text = await response.text();
        errorDetail = `상세 내용: ${text.slice(0, 200)}`;
      } catch {
        errorDetail = `상세 내용: ${response.statusText}`;
      }
    }

    throw new Error(
      `네이버 쇼핑 스킬 API 호출 실패 [HTTP ${response.status} ${response.statusText}]\n` +
      `요청 URL: ${url.toString()}\n` +
      `${errorDetail}\n` +
      `참고: 네이버 검색 API 종료 또는 프록시 엔드포인트 변경으로 인해 요청이 거부되었을 수 있습니다.`
    );
  }

  let data;
  try {
    data = await response.json();
  } catch (err) {
    throw new Error(`응답 본문을 JSON으로 파싱할 수 없습니다: ${err.message}`);
  }

  return data;
}

async function runBot() {
  console.log("=".repeat(65));
  console.log(" 🛒  [lowprice_bot] 물티슈 최저가 알림 봇 시작");
  console.log(` 🔍  검색 키워드: '${KEYWORD}' | 정렬: ${SORT_ORDER} (최저가순)`);
  console.log(` 🎯  목표 가격: ${TARGET_PRICE.toLocaleString()}원 이하`);
  console.log(` 🌐  엔드포인트: ${API_URL}`);
  console.log("=".repeat(65));

  // 1. 네이버 쇼핑 검색 스킬로 데이터 수집
  let rawData;
  if (process.argv.includes("--demo") || process.argv.includes("--mock")) {
    console.log("\n🧪 [데모/테스트 모드 실행 - 광고 필터링 및 정상 출력 시연]");
    rawData = {
      items: [
        {
          title: "[광고] 베베앙 물티슈 70매 10팩 타임특가",
          price: 8900,
          mall_name: "광고대행스토어",
          review_count: 12,
          is_ad: true,
          url: "https://shopping.naver.com/ad_sample",
        },
        {
          title: "베베앙 물티슈 캡형 75평량 70매 20팩",
          price: 16400,
          mall_name: "베베앙 공식 브랜드스토어",
          review_count: 18520,
          is_ad: false,
          url: "https://shopping.naver.com/catalog/sample1",
        },
        {
          title: "베베앙 프리미엄 골드 82평량 70매 20팩",
          price: 17900,
          mall_name: "11번가",
          review_count: 9430,
          is_ad: false,
          url: "https://shopping.naver.com/catalog/sample2",
        },
        {
          title: "(광고) 베베앙 물티슈 파워딜",
          price: 15000,
          mall_name: "오픈마켓 [광고]",
          review_count: 45,
          is_ad: false,
          url: "https://shopping.naver.com/ad_sample2",
        },
        {
          title: "베베앙 시그니처 캡형 100매 20팩",
          price: 26500,
          mall_name: "G마켓",
          review_count: 6210,
          is_ad: false,
          url: "https://shopping.naver.com/catalog/sample3",
        },
        {
          title: "베베앙 오리지널 플러스 100매 20팩",
          price: 28900,
          mall_name: "옥션",
          review_count: 3150,
          is_ad: false,
          url: "https://shopping.naver.com/catalog/sample4",
        },
      ],
    };
  } else {
    try {
      rawData = await fetchNaverShopping(KEYWORD, SORT_ORDER, FETCH_LIMIT);
    } catch (err) {
      console.error("\n❌ [오류 발생 - 스킬 호출 실패]");
      console.error("잘못된 값이나 오류가 발생하여 임의의 값을 지어내지 않고 처리를 중단합니다.");
      console.error("-".repeat(65));
      console.error(err.message);
      console.error("-".repeat(65));
      console.error("봇을 종료합니다 (종료 코드: 1).");
      process.exit(1);
    }
  }

  // 2. 반환 데이터 무결성 검증
  if (!rawData || typeof rawData !== "object") {
    console.error("\n❌ [오류 발생 - 데이터 형식 불일치]");
    console.error(`응답 데이터가 올바른 JSON 객체 형태가 아닙니다.`);
    console.error("잘못된 데이터를 임의로 보정하지 않고 즉시 멈춥니다.");
    process.exit(1);
  }

  const items = rawData.items;
  if (!Array.isArray(items)) {
    console.error("\n❌ [오류 발생 - 상품 목록 부재]");
    console.error("응답 내에 'items' 목록이 존재하지 않거나 올바르지 않습니다.");
    console.error(`응답 키 목록: ${Object.keys(rawData).join(", ")}`);
    console.error("잘못된 데이터이므로 임의로 생성하지 않고 즉시 멈춥니다.");
    process.exit(1);
  }

  if (items.length === 0) {
    console.error("\n❌ [오류 발생 - 검색 결과 0건]");
    console.error(`'${KEYWORD}'에 대한 검색 결과가 0건입니다.`);
    console.error("잘못된 검색 결과를 지어내지 않고 즉시 멈춥니다.");
    process.exit(1);
  }

  // 3. 광고 상품 필터링 및 데이터 정제
  const filteredItems = [];
  let adCount = 0;

  for (const item of items) {
    if (isAdvertisement(item)) {
      adCount++;
      continue;
    }

    const title = cleanHtml(item.title);
    const mallName = item.mall_name || item.mallName || "판매처 정보 없음";
    const link = item.url || item.link || "";

    const priceRaw = item.price ?? item.lprice;
    if (priceRaw === undefined || priceRaw === null) continue;

    let price;
    try {
      price = parsePrice(priceRaw);
    } catch {
      continue;
    }

    if (price <= 0) continue;

    const reviewCount = parseReviewCount(item.review_count ?? item.reviewCount);

    filteredItems.push({
      title,
      price,
      mall_name: mallName,
      review_count: reviewCount,
      link,
    });
  }

  console.log(`\n📊 총 수신 상품: ${items.length}개 | 광고 제외: ${adCount}개 | 유효 상품: ${filteredItems.length}개`);

  if (filteredItems.length === 0) {
    console.error("\n❌ [오류 발생 - 유효 상품 없음]");
    console.error("수신된 상품이 모두 광고이거나 올바른 가격 정보가 없습니다.");
    console.error("가짜 상품을 지어내지 않고 처리를 중단합니다.");
    process.exit(1);
  }

  // 가격 오름차순 정렬
  filteredItems.sort((a, b) => a.price - b.price);

  // 상위 TOP_N(3개) 추출
  const topItems = filteredItems.slice(0, TOP_N);

  // 4. 화면에 보기 좋게 출력
  console.log("\n" + "=".repeat(65));
  console.log(` 🏆  [베베앙 20개 최저가 순위 TOP ${topItems.length}]`);
  console.log("=".repeat(65));

  topItems.forEach((prod, idx) => {
    const rank = idx + 1;
    console.log(`\n[${rank}위] ${prod.title}`);
    console.log(`  • 가  격 : ${prod.price.toLocaleString()}원`);
    console.log(`  • 판매처 : ${prod.mall_name}`);
    console.log(`  • 리뷰수 : ${prod.review_count.toLocaleString()}개`);
    console.log(`  • 링크   : ${prod.link}`);
    console.log("  " + "-".repeat(60));
  });

  // 5. 1위 가격과 목표가(20,000원) 비교 및 알림 문구 출력
  const lowestProduct = topItems[0];
  const lowestPrice = lowestProduct.price;

  console.log("\n" + "=".repeat(65));
  console.log(" 📢  [목표 가격 달성 여부]");
  console.log(`  • 1위 최저가: ${lowestPrice.toLocaleString()}원 (목표가: ${TARGET_PRICE.toLocaleString()}원)`);

  let statusMsg = "";
  if (lowestPrice <= TARGET_PRICE) {
    statusMsg = "[특가발견] 목표 가격 이하입니다!";
  } else {
    statusMsg = "[유지] 아직 목표 가격 보다 비싸요!";
  }

  console.log(`  • 판    정 : ${statusMsg}`);
  console.log("=".repeat(65));
}

runBot();
