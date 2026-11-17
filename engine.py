"""MediCheck MVP: official I0030 reader + conservative text rule engine.

This program NEVER assesses medical suitability, lawfulness, or medication changes.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import quote

import requests

I0030_DOC_URL = "https://www.foodsafetykorea.go.kr/api/openApiInfo.do?svc_no=I0030"
API_BASE = "https://openapi.foodsafetykorea.go.kr/api"
MAX_ROWS = 20

class DataLookupError(Exception):
    """Safe, user-facing errors: do not leak the secret-bearing URL."""


@dataclass
class Product:
    product_name: str
    maker: str
    report_no: str
    functionality: str
    precautions: str
    category: str
    last_updated: str
    production_end: str
    source: str
    raw: dict[str, Any]


def parse_product(row: dict, source: str) -> Product:
    return Product(
        product_name=str(row.get('PRDLST_NM') or '').strip(),
        maker=str(row.get('BSSH_NM') or '').strip(),
        report_no=str(row.get('PRDLST_REPORT_NO') or '').strip(),
        functionality=str(row.get('PRIMARY_FNCLTY') or '').strip(),
        precautions=str(row.get('IFTKN_ATNT_MATR_CN') or '').strip(),
        category=str(row.get('PRDLST_CDNM') or '').strip(),
        last_updated=str(row.get('LAST_UPDT_DTM') or '').strip(),
        production_end=str(row.get('PRODUCTION') or '').strip(),
        source=source,
        raw=row,
    )


def normalize(text: str) -> str:
    return re.sub(r'[\s\W_]+', '', (text or '').lower(), flags=re.UNICODE)


def _filter_products(rows: list[dict], name: str, report_no: str, maker: str) -> list[dict]:
    name_n, no_n, maker_n = normalize(name), normalize(report_no), normalize(maker)
    # For report no search use ONLY exact match, never substring/fuzzy.
    if no_n:
        rows = [r for r in rows if normalize(r.get('PRDLST_REPORT_NO', '')) == no_n]
    if name_n:
        rows = [r for r in rows if name_n in normalize(r.get('PRDLST_NM',''))]
    if maker_n:
        rows = [r for r in rows if maker_n in normalize(r.get('BSSH_NM',''))]
    return rows


def search_snapshot(snapshot: dict, name: str, report_no: str = '', maker: str = '') -> list[Product]:
    rows = snapshot.get('I0030', {}).get('row', [])
    return [parse_product(r, 'snapshot') for r in _filter_products(rows, name, report_no, maker)]


def search_live(api_key: str, name: str = '', report_no: str = '', maker: str = '', session=None) -> tuple[list[Product], str]:
    """Use authenticated server-side I0030 query. No unknown filter 'all products'."""
    if not api_key or not (name.strip() or report_no.strip()):
        raise DataLookupError('인증키와 제품명 또는 품목제조번호를 입력해 주세요.')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{8,128}', api_key.strip()):
        raise DataLookupError('인증키 형식을 확인해 주세요. 키를 화면이나 채팅에 공개하지 마세요.')
    if len(name) > 120 or len(report_no) > 50 or len(maker) > 120:
        raise DataLookupError('검색어가 너무 깁니다.')
    primary_key = 'PRDLST_REPORT_NO' if report_no.strip() else 'PRDLST_NM'
    term = report_no.strip() if report_no.strip() else name.strip()
    # Encode the filter *value* in the path, not as the URL query string.
    path = f'{primary_key}={quote(term, safe="")}'
    url = f'{API_BASE}/{quote(api_key.strip(),safe="")}/I0030/json/1/{MAX_ROWS}/{path}'
    http = session or requests
    try:
        res = http.get(url, timeout=(6, 15), allow_redirects=False)
        if res.status_code in (301, 302, 303, 307, 308):
            raise DataLookupError('식약처 API 접속 주소가 변경되었습니다. 공식 서비스 주소를 확인하세요.')
        if res.status_code != 200:
            raise DataLookupError(f'식약처 응답 오류(HTTP {res.status_code}). 잠시 후 다시 확인하세요.')
        payload = res.json()
    except DataLookupError:
        raise
    except (requests.RequestException, ValueError):
        raise DataLookupError('식약처 API 연결 또는 응답 해석에 실패했습니다. 키를 포함한 주소를 공유하지 마세요.') from None
    data = payload.get('I0030') or {}
    status = (data.get('RESULT') or {}).get('CODE', '')
    if status and status != 'INFO-000':
        msgs = {
            'INFO-100': '인증키가 유효하지 않습니다.',
            'INFO-110': 'I0030 서비스 활용신청이 확인되지 않습니다.',
            'INFO-120': '서비스 승인 상태를 확인해 주세요.',
            'INFO-200': '해당 조건의 검색결과가 없습니다.',
            'INFO-300': 'API 호출 한도를 초과했습니다.',
            'INFO-320': 'API 시간당 호출 제한에 도달했습니다.',
        }
        if status == 'INFO-200':
            return [], status
        raise DataLookupError(msgs.get(status, f'식약처 API 오류 코드: {status}'))
    rows = data.get('row') or []
    # Client-side secondary verification of all requested constraints.
    filtered = _filter_products(rows, name, report_no, maker)
    return [parse_product(r, 'live') for r in filtered], status or 'INFO-000'


# Rule engine: a first-pass risk screening, not regulatory adjudication.
CURE = re.compile(r'완치|치료(?:해|하|가|됩|된|할|효과|제)?|치유|병원\s*(?:갈\s*)?필요\s*없', re.I)
DISEASE = re.compile(r'고혈압|당뇨|암|치매|독감|감기|관절염|불면증|뇌졸중|질병|병을', re.I)
PREVENTION = re.compile(r'예방|막아준|예방한다', re.I)
DRUG_STOP = re.compile(r'(?:처방약|혈압약|당뇨약|감기약|수면제|항응고제|약\s*(?:을|도|은|을요)?).{0,16}(?:끊|중단|대신|필요\s*없|안\s*먹)', re.I)
DRUG_STOP_NEGATION = re.compile(r'끊지\s*마|중단하지\s*마|대체하지\s*마|끊으면\s*안\s*됩', re.I)
QUANTIFIED = re.compile(r'\d+(?:\.\d+)?\s*(?:배|%|퍼센트)|\d+\s*(?:일|시간|주|개월)\s*(?:만에|안에)|반드시|무조건|100\s*%|즉시', re.I)
# Common legal warning on packaged foods. This is NOT a claim that a food cures a disease.
NON_MEDICINE_NOTICE = re.compile(r'질병.{0,18}(?:예방.{0,8})?치료.{0,25}의약품.{0,8}아니', re.I)
NEGATED_CURE = re.compile(r'(?:완치|치료).{0,10}(?:되지\s*않|하지\s*않|못합니다|없습니다|아닙니다)', re.I)

FUNCTIONS = {
    '면역력': [r'면역력',r'면역\s*기능'],
    '피로 개선': [r'피로'],
    '혈액흐름': [r'혈액\s*흐름',r'혈행',r'혈액\s*순환',r'혈소판\s*응집'],
    '기억력': [r'기억력'],
    '항산화': [r'항산화',r'유해\s*산소'],
    '장 건강': [r'배변',r'장\s*건강',r'유산균\s*증식',r'유해균'],
    '철 흡수': [r'철의?\s*흡수'],
    '결합조직': [r'결합조직'],
    '관절 건강': [r'관절\s*(?:및\s*연골\s*)?건강'],
    '눈 건강': [r'눈\s*건강'],
    '간 건강': [r'간\s*건강'],
}
HELP = re.compile(r'도움|필요|기여|유지|보호', re.I)


def split_claims(text: str) -> list[str]:
    # Split without altering source text; do not split function phrases such as '혈액흐름'.
    chunks = re.split(r'[.!?\n;]+|(?:\s*그리고\s*)|(?:\s*또한\s*)', text or '')
    result=[]
    for chunk in chunks:
        chunk=chunk.strip(' \t,')
        if chunk:
            result.append(chunk[:800])
    return result[:30]


def _features(text: str) -> set[str]:
    return {k for k,patterns in FUNCTIONS.items() if any(re.search(p,text,re.I) for p in patterns)}


def evaluate_ad(ad_text: str, product: Product | None, link_confirmed: bool) -> dict:
    claims = split_claims(ad_text)
    evidence = product.functionality if product else ''
    official_features = _features(evidence)
    items = []
    for claim in claims:
        reasons = []
        flags = []
        non_medicine_notice = bool(NON_MEDICINE_NOTICE.search(claim) or NEGATED_CURE.search(claim))
        if CURE.search(claim) and (DISEASE.search(claim) or '완치' in claim or '치료' in claim) and not non_medicine_notice:
            reasons.append('질병 치료·완치 효과를 단정하는 표현이 있습니다.')
            flags.append('DISEASE_TREATMENT')
        if DISEASE.search(claim) and PREVENTION.search(claim) and not non_medicine_notice:
            reasons.append('질병 예방을 단정하는 표현은 별도의 근거 확인이 필요합니다.')
            flags.append('DISEASE_PREVENTION')
        if DRUG_STOP.search(claim) and not DRUG_STOP_NEGATION.search(claim):
            reasons.append('의약품 중단 또는 대체를 권유하는 표현이 있습니다. 임의로 처방약을 중단하지 마세요.')
            flags.append('MEDICINE_SUBSTITUTION')
        if flags:
            status='CAUTION'
        elif non_medicine_notice:
            status='NEEDS_CHECK'
            reasons.append('의약품이 아니라는 안내나 치료 효과를 부정하는 문장일 수 있습니다. 이를 치료 효능 주장으로 분류하지 않습니다.')
            flags.append('NEGATED_OR_NOTICE')
        elif QUANTIFIED.search(claim):
            status='NEEDS_CHECK'
            reasons.append('효과의 크기나 기간을 단정하는 표현입니다. 해당 수치의 공식 근거를 확인하지 못했습니다.')
            flags.append('QUANTIFIED_OR_GUARANTEED')
        elif not product or not link_confirmed:
            status='NEEDS_CHECK'
            reasons.append('광고와 동일한 제품인지 확정되지 않아 공식 기능성과 비교할 수 없습니다.')
            flags.append('UNLINKED')
        elif not evidence:
            status='NEEDS_CHECK'
            reasons.append('해당 제품의 공식 기능성 정보가 비어 있습니다.')
            flags.append('NO_OFFICIAL_CLAIM')
        else:
            ad_features = _features(claim)
            if ad_features and ad_features.issubset(official_features) and HELP.search(claim):
                status='POSSIBLY_MATCHED'
                reasons.append('광고에서 언급한 기능이 이 제품의 공식 기능성 문구에도 나타납니다. 다만 광고의 적법성·실제 효과·안전성을 보증하지 않습니다.')
                flags.append('WORDING_SUPPORTED')
            else:
                status='NEEDS_CHECK'
                reasons.append('확인된 제품별 기능성만으로 이 광고 표현을 뒷받침하기 어렵습니다.')
                flags.append('EVIDENCE_INSUFFICIENT')
        items.append({'claim':claim,'status':status,'reasons':reasons,'flags':flags})

    if not items:
        overall='NEEDS_CHECK'
    elif any(i['status']=='CAUTION' for i in items):
        overall='CAUTION'
    elif any(i['status']=='NEEDS_CHECK' for i in items):
        overall='NEEDS_CHECK'
    else:
        overall='POSSIBLY_MATCHED'
    # Strong medicine stop caveat when present, even without product match.
    return {
        'overall':overall,
        'claims':items,
        'source': product.source if product else None,
        'report_no': product.report_no if product else None,
        'link_confirmed': bool(link_confirmed),
        'disclaimer':'이 결과는 광고 표현의 예비 확인입니다. 제품의 안전성·치료 효과·광고의 법적 적법성을 확정하지 않습니다.',
    }


def date_display(value: str) -> str:
    return f'{value[:4]}-{value[4:6]}-{value[6:8]}' if re.fullmatch(r'\d{8}', value or '') else (value or '미표시')
