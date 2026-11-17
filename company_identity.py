"""Company labels extracted from an image, without guessing identities from search results.

OCR text is NOT proof the real package contains that label; photo review and
user confirmation remain mandatory before suggesting an official-claim match.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

_LABELS = re.compile(
    r'(제조\s*(?:및|·|/|&)\s*판매\s*(?:원|업소|업체)|제조판매원|'
    r'제조\s*(?:원|업소|업체|사)|유통전문판매원|판매\s*(?:원|업소|업체))\s*[:：]?\s*',
    re.I,
)
_STOP = re.compile(r'\s*(?:/|\||;|；|,|，|\n|\r|(?:\s{2,})|\(|\)|소재지\s*[:：]|주소\s*[:：]|전화\s*[:：]|고객센터\s*[:：])')
_CORP = re.compile(r'^(?:(?:\(\s*주\s*\)|㈜|주식회사)\s*)?[가-힣A-Za-z0-9]+(?:[\s.-][가-힣A-Za-z0-9]+){0,5}')


def normalized(value: str) -> str:
    return re.sub(r'[\W_]+', '', (value or '').casefold(), flags=re.UNICODE)


@dataclass(frozen=True)
class CompanyMention:
    name: str
    role: str  # 'manufacturer' / 'seller' / 'combined'
    evidence: str


def _role(label: str) -> str:
    l = re.sub(r'\s+', '', label)
    if ('제조' in l and '판매' in l):
        return 'combined'
    return 'seller' if '판매' in l else 'manufacturer'


def _valid_name(text: str) -> bool:
    n = normalized(text)
    return 2 <= len(n) <= 65 and not n.isdigit()


def find_labeled_companies(full_text: str) -> list[CompanyMention]:
    """Only recover company names adjacent to explicitly labeled company roles."""
    text = full_text or ''
    result: list[CompanyMention] = []
    for m in _LABELS.finditer(text):
        tail = text[m.end():m.end()+85].lstrip(' \t:-')
        # Stop before another labeled role or contact/ingredient information.
        nextlabel = _LABELS.search(tail)
        if nextlabel:
            tail = tail[:nextlabel.start()]
        for stop in ('소재지', '주소', '연락처', '전화번호', '고객센터', '대표번호', '유통기한', '내용량', '서울특별시', '부산광역시', '인천광역시', '경기도'):
            p = tail.find(stop)
            if p >= 0:
                tail = tail[:p]
        # Parentheses are permitted only as the (주) prefix; delimit before address etc.
        tail = re.split(r'\s+[/|;；,，]\s*|[\n\r]', tail, maxsplit=1)[0]
        name_match = _CORP.match(tail.strip())
        if not name_match:
            continue
        name = name_match.group(0).strip(' .-')
        # Strip labels accidentally swallowed into a multiword company name.
        name = re.split(r'\s+(?:제조|판매|품목|대표|고객|서울|부산|경기|인천|광주|대구|대전|울산|세종|충청|경상|전라|강원|제주)(?:\s|$)',name)[0].strip()
        if not _valid_name(name):
            continue
        ev = text[m.start():m.end()] + name
        item = CompanyMention(name, _role(m.group(1)), ev)
        if not any(x.role==item.role and normalized(x.name)==normalized(item.name) for x in result):
            result.append(item)
    return result


def verify_company_ocr(parsed: dict, full_text: str) -> dict:
    """Validate extracted company against company-labeled spans in model OCR text.

    A name seen ONLY in an official search result or untitled OCR region is not
    accepted as manufacturer evidence. Seller-only evidence stays seller-only.
    """
    mentions = find_labeled_companies(full_text)
    def choose(role: str, candidate: str) -> CompanyMention | None:
        eligible = [m for m in mentions if m.role == role]
        if candidate:
            exact = [m for m in eligible if normalized(m.name)==normalized(candidate)]
            if exact:
                return exact[0]
        # Only infer automatically when there is an unambiguous name for that role.
        if len(eligible)==1:
            return eligible[0]
        return None

    raw_manufacturer = str(parsed.get('manufacturer') or '').strip()
    raw_seller = str(parsed.get('seller') or '').strip()
    raw_combined = str(parsed.get('combined_company') or '').strip()
    man = choose('manufacturer',raw_manufacturer)
    combined = choose('combined', raw_combined or raw_manufacturer)
    seller = choose('seller',raw_seller)
    # Never override conflicting explicit manufacturer and combined labels.
    if man and combined and normalized(man.name)!=normalized(combined.name):
        combined=None
    effective = man or combined
    return {
        'manufacturer': effective.name if effective else '',
        'manufacturer_verified': bool(effective),
        'manufacturer_evidence': effective.evidence if effective else '',
        'seller': seller.name if seller else '',
        'seller_verified': bool(seller),
        'seller_evidence': seller.evidence if seller else '',
        'combined_company':combined.name if combined else '',
        'combined_verified':bool(combined),
        'combined_evidence':combined.evidence if combined else '',
        'company_role': 'manufacturer' if man else ('combined' if combined else ('seller' if seller else 'unknown')),
    }
