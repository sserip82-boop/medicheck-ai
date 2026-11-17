from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from senior_ui import build_spoken_summary,voice_player_html

class P:
    product_name='관절팔팔'


def test_speech_includes_context_and_caution():
    result={'overall':'CAUTION','claims':[{'claim':'고혈압이 완치된다','reasons':['질병 치료 효과를 단정하는 표현입니다.']} ]}
    s=build_spoken_summary(result,P(),True)
    assert '광고 표현에 주의' in s and '관절팔팔' in s and '처방약' in s


def test_unlinked_claim_caveat():
    s=build_spoken_summary({'overall':'NEEDS_CHECK','claims':[]},P(),False)
    assert '같은지 아직 확인되지' in s


def test_escapes_script_breakout():
    html=voice_player_html('</script><script>alert(42)</script>')
    assert '</script><script>alert(42)' not in html
    assert chr(92)+'u003c' in html
    assert 'speechSynthesis' in html


def test_ko_language_and_buttons():
    html=voice_player_html('안녕하세요')
    assert "utterance.lang='ko-KR'" in html
    assert '결과 듣기' in html and '읽기 중지' in html
