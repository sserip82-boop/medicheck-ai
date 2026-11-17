"""Conservative filters for advertisements OCR text. No medical adjudication."""
from __future__ import annotations
import re
from collections.abc import Iterable

MAX_CLAIMS = 12
# Sections that describe safe use, ingredients, business details; not efficacy promises.
EXCLUSIONS = re.compile(
    r'섭취(?:량|방법|시|할|를|전|후)|복용(?:시|량|방법)|보관|주의사항|주의하십시오|알레르기|'
    r'이상사례|의약품.{0,14}아닙니다|질병.{0,30}의약품.{0,15}아니|'
    r'원재료|원료명|영양정보|영양성분|제조(?:원|사|업소|일|번호)|유통기한|소비기한|'
    r'품목제조|판매원|포장재|고객센터|문의처|반품|교환|연락처|냉장|직사광선|'
    r'알코올|칼로리|나트륨|탄수화물|단백질|지방|당류|열량|내용량|중량|'
    r'품질유지|색상|성상|섭씨|유산균수|일일섭취',
    re.I,
)
# Includes explicit assertions about treatment, cures, drug stopping.
PROMISE = re.compile(
    r'도움|개선|증진|효과|건강|항산화|보호|예방|완치|치료|낫(?:습|는|게|는다)|'
    r'(?:혈압|혈당|콜레스테롤|통증|관절|면역력|기억력|피로|혈액흐름|혈행|근육|치매|당뇨|고혈압|암)'
    r'.{0,28}(?:좋|줄|낮|높|개선|완치|치료|예방|해소)|'
    r'(?:약|처방약|혈압약|당뇨약).{0,15}(?:끊|중단|대신|필요\s*없)',
    re.I,
)
# Safety instructions containing treatment words should not be promoted as claims.
CAVEAT = re.compile(r'질병.{0,25}(?:예방|치료).{0,25}의약품.{0,12}아니', re.I)

def compact(value: str) -> str:
    return re.sub(r'[\W_]+', '', (value or '').casefold(), flags=re.UNICODE)


def looks_like_promotional_claim(value: str) -> bool:
    text = (value or '').strip()
    if not 5 <= len(text) <= 220:
        return False
    if CAVEAT.search(text):
        return False
    if EXCLUSIONS.search(text):
        return False
    if not PROMISE.search(text):
        return False
    # A non-promotional instruction containing an efficacy word is not an ad claim.
    if re.search(r'(?:중단|끊|대체)(?:하지|지)\s*마|문제가\s*발생|전문가와\s*상담', text):
        return False
    return True


def validate_claim_quotes(full_text: str, proposals: Iterable[str] | None) -> list[str]:
    """Accept only quoted text actually present in OCR; never accept AI inventions.

    This is a lightweight source-faithfulness check, not proof OCR read the photo correctly.
    """
    source = compact(full_text)
    result: list[str] = []
    seen: set[str] = set()
    if not source or isinstance(proposals, str):
        return result
    for candidate in proposals or []:
        if not isinstance(candidate, str):
            continue
        candidate = candidate.strip(' \t\r\n•-·')
        key = compact(candidate)
        if not key or key in seen:
            continue
        if key not in source or not looks_like_promotional_claim(candidate):
            continue
        result.append(candidate)
        seen.add(key)
        if len(result) >= MAX_CLAIMS:
            break
    return result


def merge_claims(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for group in groups:
        for claim in group:
            key = compact(claim)
            if key and key not in seen:
                result.append(claim)
                seen.add(key)
            if len(result) >= MAX_CLAIMS:
                return result
    return result
