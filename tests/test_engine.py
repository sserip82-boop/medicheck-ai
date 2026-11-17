import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from engine import search_snapshot, evaluate_ad, Product, search_live, DataLookupError

SNAP=json.loads((Path(__file__).parents[1]/'demo_i0030.json').read_text(encoding='utf-8'))
P=search_snapshot(SNAP,'6년근 홍삼 자신만만 홍삼스틱')[0]

def test_sample_rows():
    assert len(SNAP['I0030']['row']) == 5
    assert P.report_no=='20040015100230'
    assert '혈액흐름' in P.functionality

def test_report_exact_match():
    assert len(search_snapshot(SNAP,'',report_no='20040015100230'))==1
    assert search_snapshot(SNAP,'',report_no='2004001510023')==[]

def test_name_maker_matching():
    assert len(search_snapshot(SNAP,'홍삼스틱',maker='일화')) == 1
    assert search_snapshot(SNAP,'홍삼스틱',maker='다른회사')==[]

def test_cure_and_medicine_stop():
    r=evaluate_ad('이 홍삼스틱을 먹으면 고혈압이 완치되고 혈압약도 끊을 수 있습니다.',P,True)
    assert r['overall']=='CAUTION'
    assert {'DISEASE_TREATMENT','MEDICINE_SUBSTITUTION'} <= set(r['claims'][0]['flags'])

def test_function_matches_only_with_confirmation():
    assert evaluate_ad('면역력 증진에 도움을 줄 수 있습니다.',P,True)['overall']=='POSSIBLY_MATCHED'
    assert evaluate_ad('면역력 증진에 도움을 줄 수 있습니다.',P,False)['overall']=='NEEDS_CHECK'

def test_bloodpressure_not_bloodflow():
    assert evaluate_ad('혈압 관리에 도움이 됩니다.',P,True)['overall']=='NEEDS_CHECK'

def test_quantified_claim_not_safe():
    assert evaluate_ad('기억력이 2배 좋아집니다.',P,True)['overall']=='NEEDS_CHECK'

def test_medication_safety_warning_without_product():
    assert evaluate_ad('혈압약 대신 드세요.',None,False)['overall']=='CAUTION'

def test_negative_warning_doesnt_trigger_stop():
    result=evaluate_ad('혈압약을 끊지 마세요.',P,True)
    assert result['overall'] != 'CAUTION'

def test_no_claims():
    assert evaluate_ad('',P,True)['overall']=='NEEDS_CHECK'

class FakeResponse:
    status_code=200
    def json(self):
        return {'I0030': {'RESULT':{'CODE':'INFO-000'},'row':[P.raw]}}
class FakeSession:
    def get(self,url,**kwargs):
        assert '/I0030/json/1/20/' in url
        assert 'PRDLST_REPORT_NO=20040015100230' in url
        return FakeResponse()

def test_mocked_live_lookup():
    products, status=search_live('a'*20, report_no='20040015100230',session=FakeSession())
    assert status=='INFO-000'
    assert len(products)==1 and products[0].source=='live'


def test_food_disclaimer_not_cure_claim():
    r=evaluate_ad('질병의 예방 및 치료를 위한 의약품이 아닙니다.', P, True)
    assert r['overall'] != 'CAUTION'
    assert 'DISEASE_TREATMENT' not in r['claims'][0]['flags']


def test_explicit_no_cure_not_cure_claim():
    r=evaluate_ad('고혈압은 이 제품으로 완치되지 않습니다.', P, True)
    assert r['overall'] != 'CAUTION'
