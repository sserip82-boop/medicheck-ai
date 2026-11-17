from io import BytesIO
import sys
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0, str(Path(__file__).parents[1]))
from vision import photo_text_ocr, DEFAULT_GEMINI_MODEL


def tiny_png():
    im = Image.new('RGB', (80, 50), 'white')
    buf = BytesIO()
    im.save(buf, format='PNG')
    return buf.getvalue()


class Response:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self.data = data or {'candidates':[{'content':{'parts':[{'text':'{"product_name":"홍삼스틱", "manufacturer":"(주)일화", "report_no":"20040015100230", "full_text":"홍삼스틱"}'}]}}]}
    def json(self):
        return self.data


class FakeHTTP:
    def __init__(self, status=200, data=None):
        self.status = status
        self.data = data
    def post(self, url, headers, json, timeout, allow_redirects):
        assert url == f'https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_GEMINI_MODEL}:generateContent'
        assert headers['x-goog-api-key'] == 'test-key'
        assert 'Authorization' not in headers
        assert json['generationConfig']['responseMimeType'] == 'application/json'
        assert json['contents'][0]['parts'][1]['inline_data']['mime_type'] == 'image/jpeg'
        assert len(json['contents'][0]['parts'][1]['inline_data']['data']) > 30
        assert allow_redirects is False
        return Response(status=self.status, data=self.data)


def test_gemini_ocr_parses_json_and_prepares_image():
    result = photo_text_ocr(tiny_png(), 'test-key', 'product', transport=FakeHTTP())
    assert result['product_name'] == '홍삼스틱'
    assert result['manufacturer'] == '(주)일화'
    assert result['report_no'] == '20040015100230'
    assert result['claim_candidates'] == []


def test_ad_ocr_fields():
    data={'candidates':[{'content':{'parts':[{'text':'{"full_text":"고혈압 완치", "mentioned_product_name":"홍삼스틱"}'}]}}]}
    result=photo_text_ocr(tiny_png(),'test-key','ad',transport=FakeHTTP(data=data))
    assert result == {'full_text':'고혈압 완치', 'mentioned_product_name':'홍삼스틱', 'claim_candidates': []}


def test_no_key_does_not_send():
    with pytest.raises(RuntimeError, match='Gemini'):
        photo_text_ocr(tiny_png(), '', 'product')


def test_too_large_image_rejected():
    with pytest.raises(RuntimeError, match='10MB'):
        photo_text_ocr(b'0'*(10*1024*1024+1), 'test-key', 'ad')


def test_invalid_file_rejected():
    with pytest.raises(RuntimeError, match='사진을 읽을 수 없습니다'):
        photo_text_ocr(b'not an image', 'test-key', 'ad')


def test_photo_kind_invalid():
    with pytest.raises(RuntimeError, match='종류'):
        photo_text_ocr(tiny_png(), 'test-key', 'evil')


def test_invalid_model_rejected():
    with pytest.raises(RuntimeError, match='모델'):
        photo_text_ocr(tiny_png(), 'test-key', 'product', model='evil/../../path')


@pytest.mark.parametrize('status,message', [(400,'400'),(401,'인증'),(403,'인증'),(404,'404'),(429,'429'),(503,'일시적')])
def test_gemini_errors_are_user_friendly(status, message):
    with pytest.raises(RuntimeError, match=message):
        photo_text_ocr(tiny_png(),'test-key','product',transport=FakeHTTP(status=status))


def test_gemini_no_response():
    with pytest.raises(RuntimeError, match='결과'):
        photo_text_ocr(tiny_png(),'test-key','product',transport=FakeHTTP(data={'candidates':[]}))


def test_gemini_bad_json():
    data={'candidates':[{'content':{'parts':[{'text':'not-json'}]}}]}
    with pytest.raises(RuntimeError, match='형식'):
        photo_text_ocr(tiny_png(),'test-key','product',transport=FakeHTTP(data=data))


def test_gemini_flash_lite_allowed():
    class LiteHTTP(FakeHTTP):
        def post(self, url, headers, json, timeout, allow_redirects):
            assert 'gemini-2.5-flash-lite:generateContent' in url
            return Response()
    assert photo_text_ocr(tiny_png(),'test-key','product',model='gemini-2.5-flash-lite',transport=LiteHTTP())['product_name']=='홍삼스틱'


def test_gemini_extracts_only_verified_efficacy_quotes():
    import json
    full = ('섭취량 및 섭취방법 1일 2회 충분한 물과 함께 섭취하십시오. '
            '제품명 관절팔팔. 관절건강에 도움을 줄 수 있음. '
            '주의사항: 알레르기 체질의 경우 원료를 확인하세요.')
    data = {'candidates':[{'content':{'parts':[{'text':json.dumps({
        'full_text':full,
        'mentioned_product_name':'관절팔팔',
        'claim_candidates':['관절건강에 도움을 줄 수 있음',
                            '섭취량 및 섭취방법 1일 2회 충분한 물과 함께 섭취하십시오',
                            '고혈압 완치',
                            '주의사항: 알레르기 체질의 경우 원료를 확인하세요'],
    },ensure_ascii=False)}]}}]}
    out = photo_text_ocr(tiny_png(),'test-key','ad',transport=FakeHTTP(data=data))
    assert out['claim_candidates'] == ['관절건강에 도움을 줄 수 있음']
    assert '섭취량' in out['full_text']


def test_gemini_excludes_negated_safety_warning():
    import json
    full='질병의 예방 및 치료를 위한 의약품이 아닙니다. 혈압약을 끊지 마세요.'
    data={'candidates':[{'content':{'parts':[{'text':json.dumps({
        'full_text':full,'claim_candidates':['질병의 예방 및 치료를 위한 의약품이 아닙니다','혈압약을 끊지 마세요']
    },ensure_ascii=False)}]}}]}
    out=photo_text_ocr(tiny_png(),'test-key','ad',transport=FakeHTTP(data=data))
    assert out['claim_candidates']==[]
