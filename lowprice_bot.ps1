# lowprice_bot.ps1 - 네이버 쇼핑 검색 스킬 기반 물티슈 최저가 알림 봇 (PowerShell 버전)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Keyword = "베베앙 20개"
$SortOrder = "price_asc"
$FetchLimit = 20
$TargetPrice = 20000
$TopN = 3

$DefaultApiUrl = "https://k-skill-proxy.nomadamas.org/v1/naver-shopping/search"
$ApiUrl = if ($env:NAVER_SHOPPING_PROXY_URL) { $env:NAVER_SHOPPING_PROXY_URL } else { $DefaultApiUrl }

Write-Host ("=" * 65)
Write-Host " 🛒  [lowprice_bot] 물티슈 최저가 알림 봇 시작"
Write-Host " 🔍  검색 키워드: '$Keyword' | 정렬: $SortOrder (최저가순)"
Write-Host (" 🎯  목표 가격: {0:N0}원 이하" -f $TargetPrice)
Write-Host " 🌐  엔드포인트: $ApiUrl"
Write-Host ("=" * 65)

$EncodedKeyword = [System.Uri]::EscapeDataString($Keyword)
$RequestUri = "${ApiUrl}?q=${EncodedKeyword}&sort=${SortOrder}&limit=${FetchLimit}"

if ($args -contains "--demo" -or $args -contains "--mock") {
    Write-Host "`n🧪 [데모/테스트 모드 실행 - 광고 필터링 및 정상 출력 시연]" -ForegroundColor Cyan
    $Response = [PSCustomObject]@{
        items = @(
            [PSCustomObject]@{
                title = "[광고] 베베앙 물티슈 70매 10팩 타임특가"
                price = 8900
                mall_name = "광고대행스토어"
                review_count = 12
                is_ad = $true
                url = "https://shopping.naver.com/ad_sample"
            },
            [PSCustomObject]@{
                title = "베베앙 물티슈 캡형 75평량 70매 20팩"
                price = 16400
                mall_name = "베베앙 공식 브랜드스토어"
                review_count = 18520
                is_ad = $false
                url = "https://shopping.naver.com/catalog/sample1"
            },
            [PSCustomObject]@{
                title = "베베앙 프리미엄 골드 82평량 70매 20팩"
                price = 17900
                mall_name = "11번가"
                review_count = 9430
                is_ad = $false
                url = "https://shopping.naver.com/catalog/sample2"
            },
            [PSCustomObject]@{
                title = "(광고) 베베앙 물티슈 파워딜"
                price = 15000
                mall_name = "오픈마켓 [광고]"
                review_count = 45
                is_ad = $false
                url = "https://shopping.naver.com/ad_sample2"
            },
            [PSCustomObject]@{
                title = "베베앙 시그니처 캡형 100매 20팩"
                price = 26500
                mall_name = "G마켓"
                review_count = 6210
                is_ad = $false
                url = "https://shopping.naver.com/catalog/sample3"
            },
            [PSCustomObject]@{
                title = "베베앙 오리지널 플러스 100매 20팩"
                price = 28900
                mall_name = "옥션"
                review_count = 3150
                is_ad = $false
                url = "https://shopping.naver.com/catalog/sample4"
            }
        )
    }
}
else {
    try {
        $Response = Invoke-RestMethod -Uri $RequestUri -Method Get -TimeoutSec 10 -ErrorAction Stop
    }
    catch {
        Write-Host "`n❌ [오류 발생 - 스킬 호출 실패]" -ForegroundColor Red
        Write-Host "잘못된 값이나 오류가 발생하여 임의의 값을 지어내지 않고 처리를 중단합니다."
        Write-Host ("-" * 65)
        Write-Host "요청 URL: $RequestUri"
        Write-Host "오류 내용: $($_.Exception.Message)"
        if ($_.Exception.Response) {
            $StatusCode = [int]$_.Exception.Response.StatusCode
            Write-Host "HTTP 상태 코드: $StatusCode"
        }
        Write-Host "참고: 네이버 검색 API 공식 종료 또는 프록시 엔드포인트 변경으로 인해 요청이 거부되었을 수 있습니다."
        Write-Host ("-" * 65)
        Write-Host "봇을 종료합니다 (종료 코드: 1)."
        exit 1
    }
}

if (-not $Response -or -not $Response.items) {
    Write-Host "`n❌ [오류 발생 - 상품 목록 부재]" -ForegroundColor Red
    Write-Host "응답 내에 유효한 상품 목록(items)이 존재하지 않습니다."
    Write-Host "잘못된 데이터이므로 임의로 생성하지 않고 즉시 멈춥니다."
    exit 1
}

$Items = $Response.items
if ($Items.Count -eq 0) {
    Write-Host "`n❌ [오류 발생 - 검색 결과 0건]" -ForegroundColor Red
    Write-Host "'$Keyword'에 대한 검색 결과가 0건입니다."
    Write-Host "잘못된 검색 결과를 지어내지 않고 즉시 멈춥니다."
    exit 1
}

$FilteredItems = @()
$AdCount = 0

foreach ($item in $Items) {
    $isAd = ($item.is_ad -eq $true) -or ($item.ad -eq $true) -or ($item.adType)
    $title = [regex]::Replace([string]$item.title, "<[^>]+>", "").Trim()
    $mall = [string]($item.mall_name -replace '^$', ($item.mallName))

    if ($isAd -or $title.Contains("[광고]") -or $title.Contains("(광고)") -or $mall.Contains("[광고]")) {
        $AdCount++
        continue
    }

    $rawPrice = if ($null -ne $item.price) { $item.price } else { $item.lprice }
    $cleanPriceStr = [regex]::Replace([string]$rawPrice, "[^\d]", "")
    if (-not $cleanPriceStr) { continue }
    $price = [int]$cleanPriceStr
    if ($price -le 0) { continue }

    $rawReview = if ($null -ne $item.review_count) { $item.review_count } else { $item.reviewCount }
    $cleanReviewStr = [regex]::Replace([string]$rawReview, "[^\d]", "")
    $reviewCount = if ($cleanReviewStr) { [int]$cleanReviewStr } else { 0 }

    $link = if ($item.url) { $item.url } else { $item.link }

    $FilteredItems += [PSCustomObject]@{
        Title = $title
        Price = $price
        MallName = if ($mall) { $mall } else { "판매처 정보 없음" }
        ReviewCount = $reviewCount
        Link = $link
    }
}

Write-Host "`n📊 총 수신 상품: $($Items.Count)개 | 광고 제외: $AdCount`개 | 유효 상품: $($FilteredItems.Count)개"

if ($FilteredItems.Count -eq 0) {
    Write-Host "`n❌ [오류 발생 - 유효 상품 없음]" -ForegroundColor Red
    Write-Host "수신된 상품이 모두 광고이거나 올바른 가격 정보가 없습니다."
    Write-Host "가짜 상품을 지어내지 않고 처리를 중단합니다."
    exit 1
}

$SortedItems = $FilteredItems | Sort-Object -Property Price
$TopItems = $SortedItems | Select-Object -First $TopN

Write-Host "`n$("=" * 65)"
Write-Host " 🏆  [베베앙 20개 최저가 순위 TOP $($TopItems.Count)]"
Write-Host ("=" * 65)

$Rank = 1
foreach ($prod in $TopItems) {
    Write-Host "`n[${Rank}위] $($prod.Title)"
    Write-Host ("  • 가  격 : {0:N0}원" -f $prod.Price)
    Write-Host "  • 판매처 : $($prod.MallName)"
    Write-Host ("  • 리뷰수 : {0:N0}개" -f $prod.ReviewCount)
    Write-Host "  • 링크   : $($prod.Link)"
    Write-Host ("  " + ("-" * 60))
    $Rank++
}

$LowestPrice = $TopItems[0].Price
Write-Host "`n$("=" * 65)"
Write-Host " 📢  [목표 가격 달성 여부]"
Write-Host ("  • 1위 최저가: {0:N0}원 (목표가: {1:N0}원)" -f $LowestPrice, $TargetPrice)

if ($LowestPrice -le $TargetPrice) {
    $StatusMsg = "[특가발견] 목표 가격 이하입니다!"
} else {
    $StatusMsg = "[유지] 아직 목표 가격 보다 비싸요!"
}

Write-Host "  • 판    정 : $StatusMsg"
Write-Host ("=" * 65)
