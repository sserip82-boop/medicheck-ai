"""User-facing exactness assessment: search results ≠ verified package identity."""
from __future__ import annotations
from dataclasses import dataclass
import re
from engine import Product, normalize


def normalize_maker(text: str) -> str:
    text = re.sub(r'\(\s*주\s*\)|㈜|주식회사', '', text or '')
    return normalize(text)


@dataclass(frozen=True)
class MatchResult:
    level: str
    label: str
    details: str
    sufficient_for_claim_comparison: bool


def assess_product_match(product: Product, name: str, maker: str, report_no: str) -> MatchResult:
    """Evaluate user/photo fields against official data; never auto-confirm the match."""
    name, maker, report_no = (name or '').strip(), (maker or '').strip(), (report_no or '').strip()
    name_equal = bool(name) and normalize(name) == normalize(product.product_name)
    maker_equal = bool(maker) and normalize_maker(maker) == normalize_maker(product.maker)
    report_equal = bool(report_no) and report_no == product.report_no

    if report_no and not report_equal:
        return MatchResult('CONFLICT', '⛔ 신고번호 불일치', '입력한 신고번호와 공식 기록이 다릅니다. 다른 제품일 수 있습니다.', False)
    if name and not name_equal:
        # Similar partial names must not be treated as an exact match.
        return MatchResult('CONFLICT', '⛔ 제품명 불일치/부분 일치', '이름 일부가 같아도 별도 제품일 수 있습니다. 포장지의 정확한 품목명을 확인하세요.', False)
    if maker and not maker_equal:
        return MatchResult('CONFLICT', '⛔ 제조사 불일치', '제조사와 판매원은 다를 수 있습니다. 포장의 제조업체 정보를 확인해 수정하세요.', False)
    if report_equal:
        return MatchResult('REPORT', '✅ 신고번호 일치', '제품명·제조사도 입력했다면 모두 일치함을 확인했습니다. 광고 속 제품인지 마지막으로 직접 확인하세요.', True)
    if name_equal and maker_equal:
        return MatchResult('NAME_MAKER', '✅ 제품명+제조사 일치', '신고번호가 없어도 두 정보는 일치합니다. 최종적으로 포장 내용을 확인하세요.', True)
    if name_equal:
        return MatchResult('NAME_ONLY', '⚠️ 제품명만 일치', '제조사가 확인되지 않았습니다. 비슷한 이름의 다른 품목과 혼동할 수 있어 기능성 부합 판정을 보류합니다.', False)
    return MatchResult('INSUFFICIENT', '⚠️ 식별정보 부족', '제품명과 신고번호 가운데 하나는 정확히 확인해야 합니다.', False)
