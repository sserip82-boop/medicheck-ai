"""어르신용 광고 검증 결과 설명 및 브라우저 내 한국어 음성 읽기.

음성은 사용자의 기기에서 speechSynthesis로 처리하며 외부 TTS 서버로 전송하지 않습니다.
"""
from __future__ import annotations
import html
import json


def build_spoken_summary(result: dict, product=None, link_confirmed: bool=False) -> str:
    status=result.get('overall','NEEDS_CHECK')
    title={'CAUTION':'광고 표현에 주의하세요.',
           'NEEDS_CHECK':'추가 확인이 필요합니다.',
           'POSSIBLY_MATCHED':'공식 기능성과 일부 부합하는 표현이 있습니다.'}.get(status,'추가 확인이 필요합니다.')
    parts=[f'메디체크 AI 검사 결과입니다. {title}']
    if product and link_confirmed:
        parts.append(f'확인한 제품은 {product.product_name} 입니다.')
    elif product:
        parts.append('광고 속 제품과 검색한 제품이 같은지 아직 확인되지 않았습니다.')
    else:
        parts.append('공식 제품정보는 아직 연결되지 않았습니다.')
    findings=[]
    for item in result.get('claims',[])[:3]:
        claim=str(item.get('claim','')).strip()
        reasons=item.get('reasons',[])
        if claim:
            findings.append('광고 표현. '+claim[:100]+'.')
        if reasons:
            findings.append(str(reasons[0])[:150])
    parts.extend(findings)
    parts.append('이 결과는 의료 판단이나 광고의 법적 위반 여부를 확정하지 않습니다. 처방약은 광고만 보고 중단하지 마세요. 의사 또는 약사와 상담하세요.')
    return ' '.join(parts)[:1300]


def voice_player_html(spoken_text: str) -> str:
    # User-facing source text is escaped twice: JSON for JS, and prevent closing script element.
    js_text=json.dumps(spoken_text,ensure_ascii=False).replace('<', chr(92)+'u003c').replace('>',chr(92)+'u003e').replace('&',chr(92)+'u0026')
    return f'''<!doctype html><html lang="ko"><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>
    body{{font-family:system-ui,'Malgun Gothic',sans-serif;margin:0;padding:3px;color:#17324f;}}
    .actions{{display:flex;gap:10px;flex-wrap:wrap;}}
    button{{font-size:21px;font-weight:750;min-height:62px;border:2px solid #a8b8d0;background:#eef4ff;color:#18385a;border-radius:14px;padding:12px 18px;cursor:pointer;flex:1;}}
    button:focus-visible{{outline:4px solid #1261bd;outline-offset:3px;}}
    #notice{{font-size:14px;margin-top:7px;}}
    </style></head><body>
    <div class="actions"><button type="button" id="play" aria-label="검증 결과 음성으로 듣기">🔊 결과 듣기</button><button type="button" id="stop" aria-label="음성 읽기 중지">■ 읽기 중지</button></div>
    <p id="notice" aria-live="polite">휴대폰 소리 설정을 확인해 주세요.</p>
    <script>
    const txt={js_text};
    const notice=document.getElementById('notice');
    document.getElementById('play').addEventListener('click',()=>{{
      if(!('speechSynthesis' in window)){{notice.textContent='이 브라우저는 음성 읽기를 지원하지 않습니다. Chrome 또는 Safari에서 열어주세요.';return;}}
      window.speechSynthesis.cancel();
      const utterance=new SpeechSynthesisUtterance(txt);
      utterance.lang='ko-KR'; utterance.rate=0.88; utterance.pitch=1;
      const voices=window.speechSynthesis.getVoices();
      const ko=voices.find(v=>v.lang.toLowerCase().startsWith('ko'));
      if(ko) utterance.voice=ko;
      utterance.onerror=()=>{{notice.textContent='음성 재생에 실패했습니다. 기기 소리나 브라우저 설정을 확인하세요.';}};
      notice.textContent='결과를 읽는 중입니다.';
      window.speechSynthesis.speak(utterance);
    }});
    document.getElementById('stop').addEventListener('click',()=>{{
      if('speechSynthesis' in window) window.speechSynthesis.cancel();
      notice.textContent='읽기를 중지했습니다.';
    }});
    </script></body></html>'''


def render_voice_player(text: str) -> None:
    import streamlit.components.v1 as components
    components.html(voice_player_html(text),height=130,scrolling=False)
