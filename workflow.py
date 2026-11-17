"""v1.7 single-photo workflow — pure orchestration without Streamlit.

OCR only proposes claims; official identity and advertising linkage are never assumed.
The module intentionally does NOT cache images or results across users.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any

from vision import photo_text_ocr, DEFAULT_GEMINI_MODEL
from engine import Product, search_live, DataLookupError, evaluate_ad
from match_utils import assess_product_match
from claim_filter import merge_claims


@dataclass
class ScanReport:
    product_name: str = ''
    manufacturer: str = ''
    report_no: str = ''
    claim_candidates: list[str] = field(default_factory=list)
    full_text: str = ''
    products: list[Product] = field(default_factory=list)
    lookup_error: str = ''
    lookup_status: str = 'NOT_ATTEMPTED'
    source: str = 'Gemini OCR / 제품 동일성 미확인'
    seller: str = ''
    combined_company: str = ''
    manufacturer_evidence: str = ''
    seller_evidence: str = ''
    combined_evidence: str = ''
    manufacturer_verified: bool = True  # direct/explicitly user-entered records; OCR overrides this flag
    company_role: str = 'unknown'

    @property
    def claims_text(self) -> str:
        return '\n'.join(self.claim_candidates)


def _clean(value: Any, limit=300) -> str:
    return str(value or '').strip()[:limit]


def effective_manufacturer(report: ScanReport) -> str:
    """Seller-only labels are NEVER manufacturer evidence."""
    return report.manufacturer if report.manufacturer_verified else ''


def candidate_matches(report: ScanReport, product: Product):
    return assess_product_match(product, report.product_name, effective_manufacturer(report), report.report_no)


def recommended_candidate(report: ScanReport) -> Product | None:
    """Recommend ONE candidate only if a strong verified identity uniquely points to it.

    Recommendation is NOT confirmation; app must still ask the user.
    """
    strong = [p for p in report.products if candidate_matches(report,p).level in ('REPORT','NAME_MAKER')]
    if len(strong)==1:
        return strong[0]
    return None


def _sort_candidates(items: list[Product], name: str, maker: str, number: str) -> list[Product]:
    def score(p):
        match = assess_product_match(p, name, maker, number)
        weights = {'REPORT':4, 'NAME_MAKER':3, 'NAME_ONLY':1, 'INSUFFICIENT':0, 'CONFLICT':-3}
        return weights.get(match.level, 0)
    return sorted(items, key=score, reverse=True)


def lookup_products(report: ScanReport, food_key: str, searcher: Callable=search_live) -> ScanReport:
    """Update official candidates. Never silently fall back to snapshot data."""
    report.products = []
    report.lookup_error = ''
    report.lookup_status = 'NOT_ATTEMPTED'
    if not food_key:
        report.lookup_error = '식약처 서버 인증키 설정이 없습니다. 공식 제품정보는 확인하지 못했습니다.'
        report.lookup_status = 'UNAVAILABLE'
        return report
    if not (report.product_name or report.report_no):
        report.lookup_error = '사진에서 제품명 또는 신고번호를 확인하지 못했습니다.'
        report.lookup_status = 'NO_IDENTITY'
        return report
    try:
        # 신고번호 우선 검색; 조회 후 모든 후보에 대해 일치 여부를 별도 확인합니다.
        matches, status = searcher(food_key, '' if report.report_no else report.product_name,
                                   report.report_no, '')
        report.products = _sort_candidates(matches, report.product_name, effective_manufacturer(report), report.report_no)
        report.lookup_status = status or 'INFO-000'
    except DataLookupError as exc:
        report.lookup_error = str(exc)
        report.lookup_status = 'ERROR'
    return report


def scan_one_photo(data: bytes, gemini_key: str, food_key: str,
                   *, model: str = DEFAULT_GEMINI_MODEL,
                   ocr: Callable=photo_text_ocr,
                   searcher: Callable=search_live) -> ScanReport:
    """Single Gemini call and at most one I0030 query; user consent handled by UI."""
    extracted = ocr(data, gemini_key, 'single', model=model)
    raw_claims = extracted.get('claim_candidates') or []
    claims = merge_claims(raw_claims if isinstance(raw_claims, list) else [])
    report = ScanReport(
        product_name=_clean(extracted.get('product_name') or extracted.get('mentioned_product_name'), 120),
        manufacturer=_clean(extracted.get('manufacturer'), 120),
        report_no=_clean(extracted.get('report_no'), 50),
        claim_candidates=claims,
        full_text=_clean(extracted.get('full_text'), 9000),
        seller=_clean(extracted.get('seller'),120),
        combined_company=_clean(extracted.get('combined_company'),120),
        manufacturer_evidence=_clean(extracted.get('manufacturer_evidence'),250),
        seller_evidence=_clean(extracted.get('seller_evidence'),250),
        combined_evidence=_clean(extracted.get('combined_evidence'),250),
        manufacturer_verified=bool(extracted.get('manufacturer_verified', True)),
        company_role=_clean(extracted.get('company_role') or 'unknown',40),
    )
    return lookup_products(report, food_key, searcher=searcher)


def make_preliminary_result(report: ScanReport) -> dict:
    """Safe initial screening: never mark official functionality as matched yet."""
    return evaluate_ad(report.claims_text, None, False)


def selected_result(report: ScanReport, product: Product|None, confirmed: bool) -> dict:
    """Human must verify that photographed package AND advertisement are same item."""
    if product is None:
        return make_preliminary_result(report)
    match = candidate_matches(report, product)
    link_confirmed = bool(confirmed and match.sufficient_for_claim_comparison)
    return evaluate_ad(report.claims_text, product, link_confirmed)
