import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from claim_filter import looks_like_promotional_claim, validate_claim_quotes, merge_claims
from match_utils import assess_product_match
from engine import search_snapshot, evaluate_ad

ROOT=Path(__file__).parents[1]
SNAP=json.loads((ROOT/'demo_i0030.json').read_text(encoding='utf-8'))
P=search_snapshot(SNAP,'6년근 홍삼 자신만만 홍삼스틱')[0]

def test_label_exclusion_and_valuable_claim():
    assert looks_like_promotional_claim('관절건강에 도움을 줄 수 있음')
    assert not looks_like_promotional_claim('섭취량 및 섭취방법 1일 2회 1캡슐')
    assert not looks_like_promotional_claim('알레르기 체질의 경우 섭취 중단')
    assert not looks_like_promotional_claim('질병의 예방 및 치료를 위한 의약품이 아닙니다')
    assert looks_like_promotional_claim('이 제품으로 고혈압이 완치됩니다')
    assert looks_like_promotional_claim('혈압약을 끊고 이 제품을 드세요')
    assert not looks_like_promotional_claim('혈압약을 끊지 마세요')

def test_claim_quote_validation():
    text='관절건강에 도움을 줄 수 있음. 섭취량 및 섭취방법 안내.'
    assert validate_claim_quotes(text,[
        '관절건강에 도움을 줄 수 있음',
        '관절건강에 도움을 줄 수 있음',
        '섭취량 및 섭취방법 안내',
        '고혈압이 완치됩니다',
    ])==['관절건강에 도움을 줄 수 있음']

def test_merge_dedups():
    assert merge_claims(['관절건강에 도움'],['관절 건강에 도움','면역력에 도움'])==['관절건강에 도움','면역력에 도움']

def test_match_requires_two_fields_or_report():
    assert assess_product_match(P, P.product_name, '', '').level=='NAME_ONLY'
    assert not assess_product_match(P, P.product_name, '', '').sufficient_for_claim_comparison
    assert assess_product_match(P, P.product_name, P.maker, '').level=='NAME_MAKER'
    assert assess_product_match(P, P.product_name, '', P.report_no).level=='REPORT'
    assert assess_product_match(P, P.product_name, '(주)다른업체', '').level=='CONFLICT'
    assert assess_product_match(P, P.product_name+' 가짜', P.maker, '').level=='CONFLICT'
    assert assess_product_match(P, P.product_name, P.maker, P.report_no+'1').level=='CONFLICT'

def test_cannot_positive_match_name_only():
    match=assess_product_match(P,P.product_name,'','')
    result=evaluate_ad('면역력 증진에 도움을 줄 수 있습니다.',P,match.sufficient_for_claim_comparison)
    assert result['overall']=='NEEDS_CHECK'

def test_respond_to_real_joint_health_claim():
    from engine import parse_product
    record=parse_product({'PRDLST_NM':'관절팔팔','BSSH_NM':'(주)씨스팡','PRDLST_REPORT_NO':'2004001536217',
        'PRIMARY_FNCLTY':'관절건강에 도움을 줄 수 있음'},'live')
    assert assess_product_match(record,'관절팔팔','(주)씨스팡','').sufficient_for_claim_comparison
    result=evaluate_ad('관절 건강에 도움을 줄 수 있음',record,True)
    assert result['overall']=='POSSIBLY_MATCHED'
