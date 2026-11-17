"""메디체크 AI — 시연 가능한 최소 기능 웹앱(Streamlit).

실제 데이터/시연용 데이터 표시를 반드시 구분합니다.
"""
import hashlib
import hmac
from datetime import datetime
import json
import os
from pathlib import Path

import streamlit as st

from vision import photo_text_ocr, DEFAULT_GEMINI_MODEL
from claim_filter import merge_claims
from match_utils import assess_product_match
from senior_ui import build_spoken_summary, render_voice_player
from engine import (
    DataLookupError, I0030_DOC_URL, date_display, evaluate_ad,
    search_live, search_snapshot,
)

ROOT = Path(__file__).parent

st.set_page_config(page_title='메디체크 AI | 광고·제품 비교', page_icon='🛡️', layout='centered')
st.markdown('''<style>
html, body, [class*="css"] {font-family: "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;}
.block-container {max-width: 790px; padding-top: 1.4rem; padding-bottom: 3rem;}
.stButton button {min-height: 62px; font-size: 1.16rem; font-weight: 700; border-radius: 12px;}
[data-testid="stAlert"] {font-size: 1.12rem; border-radius: 12px;}
input, textarea {font-size: 1.12rem !important;}
[data-testid="stFileUploader"] {border-radius: 12px;}
.senior-headline {font-size:2rem;font-weight:800;line-height:1.4;margin:.3rem 0 1rem;}
.senior-explain {font-size:1.24rem;line-height:1.75;margin:.6rem 0 1rem;}
.senior-panel {padding:1.1rem 1.25rem;border:2px solid #d4dce8;border-radius:16px;margin:.7rem 0 1rem;}
.senior-label {font-size:1.05rem;font-weight:700;margin-bottom:.4rem;}
.senior-caution {font-size:1.14rem;font-weight:700;line-height:1.65;}
@media(max-width:650px){
  .block-container{padding-left:1rem!important;padding-right:1rem!important;padding-top:.7rem!important;}
  .senior-headline {font-size:1.67rem;}
  .senior-explain {font-size:1.14rem;}
  .stButton button {min-height:65px;width:100%;}
}
</style>''', unsafe_allow_html=True)



def secret(key):
    try:
        value = st.secrets.get(key, '')
    except Exception:  # Streamlit의 비밀설정 파일 부재 오류도 포함
        value = ''
    return str(value or os.environ.get(key, '') or '')




# 선택적 배포 시연 접속 코드: 키를 가진 불특정 다수가 API 할당량을 소진하지 않게 보호합니다.
# 공용 배포 시 Streamlit Cloud Secrets에서 APP_ACCESS_CODE를 설정하세요.
access_code_required=secret('APP_ACCESS_CODE')
if access_code_required:
    entered_code=st.text_input('시연 접속 코드',type='password',key='viewer_access_code')
    if not hmac.compare_digest(entered_code,access_code_required):
        st.title('🛡️ 메디체크 AI')
        st.write('이 시연 앱은 접속 코드가 있어야 사용할 수 있습니다.')
        if entered_code:
            st.error('접속 코드가 일치하지 않습니다.')
        st.stop()

for key,default in {
    'product_name':'',
    'maker':'', 'report_no':'', 'ad_text':'',
    'products':[], 'searched':False, 'mode_prev':None, 'searched_terms':None, 'search_iteration':0,
    'photo_fingerprint':None, 'ocr_summary':None,
}.items():
    if key not in st.session_state:
        st.session_state[key]=default

snapshot=json.loads((ROOT/'demo_i0030.json').read_text(encoding='utf-8'))

with st.sidebar:
    st.header('🔎 보기 설정')
    senior_mode=st.toggle('어르신용 큰 글씨',value=True,help='중요한 결과를 더 크게 표시하고 음성 읽기 버튼을 제공합니다.')
    st.divider()
    st.header('⚙️ 데이터·키 설정')
    # 서버 Secrets를 비밀번호 입력칸의 기본값으로 넣지 않습니다. 눈 모양을 눌러도 서버 키가 노출되지 않게 합니다.
    server_food_key=secret('FOOD_SAFETY_API_KEY')
    fs_override=st.text_input('식약처 I0030 인증키 (직접 입력할 때만)',type='password',
        placeholder='서버에 설정되어 있으면 비워 두세요',
        help='배포할 때는 Streamlit Cloud의 Secrets에 입력하세요. GitHub·스크린샷에는 포함하지 마세요.')
    fs_key=fs_override.strip() or server_food_key
    if server_food_key:
        st.caption('✅ 식약처 키가 서버에 안전하게 설정되어 있습니다. 입력칸에는 표시되지 않습니다.')
    if fs_key:
        mode=st.radio('데이터 모드', ['실시간 식약처 조회','시연용 5건 스냅샷'], index=0)
    else:
        mode='시연용 5건 스냅샷'
        st.info('식약처 인증키를 입력하거나 서버 비밀설정에 등록하면 실시간 조회가 가능합니다.')
    server_vision_key=secret('GEMINI_API_KEY')
    vision_override=st.text_input('Google Gemini API 키 (직접 입력할 때만)',type='password',
        placeholder='서버에 설정되어 있으면 비워 두세요',
        help='스마트폰 공개 배포 시에는 반드시 서버 Secrets에 등록하세요.')
    vision_key=vision_override.strip() or server_vision_key
    if server_vision_key:
        st.caption('✅ Gemini 키가 서버에 안전하게 설정되어 있습니다. 입력칸에는 표시되지 않습니다.')
    allowed_models=['gemini-3.5-flash-lite', 'gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-2.5-flash-lite']
    configured_model=secret('GEMINI_MODEL') or DEFAULT_GEMINI_MODEL
    model_index=allowed_models.index(configured_model) if configured_model in allowed_models else 0
    vision_model=st.selectbox('Gemini 사진 인식 모델',allowed_models,index=model_index)
    st.caption('Gemini API 사용량 제한·요금이 적용될 수 있습니다.')
    st.divider()
    st.markdown(f'[식약처 I0030 공식 명세]({I0030_DOC_URL})')
    st.caption('의료·법적 확정 판정을 제공하지 않습니다.')

if st.session_state['mode_prev'] != mode:
    st.session_state['products']=[]
    st.session_state['searched']=False
    st.session_state['mode_prev']=mode
    st.session_state['searched_terms']=None

st.title('🛡️ 메디체크 AI')
if senior_mode:
    st.markdown('<div class="senior-headline">건강식품 광고, 믿어도 될까요?</div>',unsafe_allow_html=True)
    st.markdown('<div class="senior-explain">① 사진 올리기 → ② 제품 찾기 → ③ 광고 표현 확인</div>',unsafe_allow_html=True)
else:
    st.markdown('### 광고에서 말하는 효과, 공식 제품정보와 같을까요?')
st.caption('카카오 AI 루키캠프 프로젝트용 MVP | 건강기능식품 조회 · 광고 문구 예비 검증')
if mode == '시연용 5건 스냅샷':
    st.warning('현재 **시연용 데이터**를 사용합니다. 2026-11-17 조회한 실제 I0030 응답 5건의 사본이며 최신 조회가 아닙니다.')
else:
    st.success('**실시간 공식 조회 모드** — 식약처 I0030에 검색 요청합니다. 이미지에서 본 제품과 같은지는 직접 확인해야 합니다.')

st.subheader('① 제품·광고 사진으로 시작하기 (선택)')
st.caption('휴대폰에서는 사진을 촬영하거나 저장된 사진을 올릴 수 있습니다. 이미지가 없어도 아래에서 직접 입력 가능합니다.')
prod_photo=st.file_uploader('제품 포장 사진', type=['jpg','jpeg','png','webp'],key='prod_photo')
ad_photo=st.file_uploader('광고 사진·캡처', type=['jpg','jpeg','png','webp'],key='ad_photo')

# 새 사진을 올리거나 교체하면, 이전 OCR 결과와 기존 제품 매칭을 사용하지 않습니다.
photo_fingerprint = (
    hashlib.sha256(prod_photo.getvalue()).hexdigest() if prod_photo else None,
    hashlib.sha256(ad_photo.getvalue()).hexdigest() if ad_photo else None,
)
if st.session_state['photo_fingerprint'] != photo_fingerprint:
    st.session_state['photo_fingerprint'] = photo_fingerprint
    st.session_state['ocr_summary'] = None
    st.session_state['products'] = []
    st.session_state['searched'] = False
    st.session_state['searched_terms'] = None
    st.session_state['search_iteration'] += 1

if prod_photo or ad_photo:
    st.caption('사진은 서버에 영구 저장하지 않습니다. 개인정보·전화번호·주소 등이 보이면 촬영 전 가려 주세요.')
    consent=st.checkbox('선택한 사진을 외부 이미지 인식 AI(Google Gemini API)에 전송하는 데 동의합니다.')
    if not vision_key:
        st.info('사진 글자 인식에는 Google AI Studio에서 발급받은 Gemini API 키가 필요합니다. 키가 없으면 아래에 직접 입력하세요.')
    if not consent:
        st.caption('동의하지 않으면 이미지를 외부 AI에 보내지 않습니다.')
    if st.button('📷 사진 글자 읽고 입력칸 채우기', disabled=not (vision_key and consent), use_container_width=True):
        try:
            extracted_prod = photo_text_ocr(prod_photo.getvalue(), vision_key, 'product', model=vision_model) if prod_photo else {}
            extracted_ad = photo_text_ocr(ad_photo.getvalue(), vision_key, 'ad', model=vision_model) if ad_photo else {}
            product_name = extracted_prod.get('product_name','').strip()
            if not product_name:
                product_name = extracted_ad.get('mentioned_product_name','').strip()
            # 사진 인식은 검색 후보를 채울 뿐, 제품 동일성이나 효능을 확정하지 않습니다.
            st.session_state['product_name'] = product_name
            st.session_state['maker'] = extracted_prod.get('manufacturer','').strip()
            st.session_state['report_no'] = extracted_prod.get('report_no','').strip()
            claims = merge_claims(
                extracted_ad.get('claim_candidates', []),
                extracted_prod.get('claim_candidates', []) if not ad_photo else [],
            )
            # 절대로 포장 뒷면 전체 OCR을 광고 문구로 자동 입력하지 않습니다.
            st.session_state['ad_text'] = '\n'.join(claims)
            st.session_state['ocr_summary'] = {
                'product_name':product_name,
                'maker':st.session_state['maker'],
                'report_no':st.session_state['report_no'],
                'ad_text':extracted_ad.get('full_text',''),
                'product_text':extracted_prod.get('full_text',''),
                'claim_candidates':claims,
                'source': '사진 문자 인식 결과 (검증되지 않음)',
            }
            st.session_state['products'] = []
            st.session_state['searched'] = False
            st.session_state['searched_terms'] = None
            st.session_state['search_iteration'] += 1
            if not claims:
                st.warning('사진 속 텍스트는 읽었지만 검증할 **효능 주장**을 확인하지 못했습니다. 섭취방법·영양정보·주의사항은 제외했습니다. 광고 문구가 있다면 아래에 직접 입력하세요.')
            else:
                st.success(f'효능 주장 {len(claims)}개만 검증 칸에 넣었습니다. OCR 원문과 비교해 확인하세요.')
            if not product_name:
                st.info('제품명을 인식하지 못했습니다. 제품명은 직접 입력할 수 있습니다.')
        except RuntimeError as exc:
            st.error(str(exc))
        except Exception:
            st.error('사진 처리 중 문제가 생겼습니다. 텍스트를 직접 입력해 주세요.')

if st.session_state['ocr_summary']:
    summary=st.session_state['ocr_summary']
    with st.expander('🔎 사진 인식 결과 확인·수정 안내', expanded=True):
        st.write('**읽힌 제품명:**',summary.get('product_name') or '인식되지 않음')
        st.write('**읽힌 제조사:**',summary.get('maker') or '인식되지 않음')
        st.write('**읽힌 신고번호:**',summary.get('report_no') or '인식되지 않음')
        claims=summary.get('claim_candidates', [])
        st.write(f'**검증 대상으로 추출한 효능 주장 ({len(claims)}개):**')
        if claims:
            for claim in claims:
                st.write('•',claim)
        else:
            st.info('효능 주장을 추출하지 않았습니다. 제품 정보·안내문을 효능 주장으로 잘못 처리하지 않도록 제외했습니다.')
        with st.expander('전체 OCR 원문 보기 (광고 검증에 자동 입력되지 않음)'):
            st.text_area('제품 사진 전체 글자', summary.get('product_text',''),height=180, disabled=True)
            st.text_area('광고 사진 전체 글자', summary.get('ad_text',''),height=180, disabled=True)
        st.warning('AI가 잘못 읽었을 수 있습니다. 아래 입력칸에서 제품명·제조사·신고번호·광고 문구를 직접 고칠 수 있습니다. 사진에 나온 제품과 공식 검색 결과가 같은지도 별도로 확인해야 합니다.')

st.subheader('② 제품 공식 정보 찾기')
def fill_sample_product():
    st.session_state['product_name']='6년근 홍삼 자신만만 홍삼스틱'
    st.session_state['maker']='(주)일화'
    st.session_state['report_no']='20040015100230'
    st.session_state['products']=[]
    st.session_state['searched']=False
    st.session_state['searched_terms']=None
    st.session_state['search_iteration']+=1
st.button('🧪 예시 제품 불러오기 (사진 없이 테스트)', on_click=fill_sample_product)
name=st.text_input('제품명', key='product_name',help='사진의 표기와 동일한 제품명을 입력하세요.')
maker=st.text_input('제조업체 (선택)',key='maker')
report=st.text_input('품목제조번호 (선택·정확한 숫자)',key='report_no')

if st.button('🔎 식약처 제품정보 조회',use_container_width=True):
    st.session_state['searched']=True
    st.session_state['searched_terms']=(name.strip(), maker.strip(), report.strip())
    st.session_state['search_iteration']+=1
    st.session_state['products']=[]
    try:
        if mode=='실시간 식약처 조회':
            products,_=search_live(fs_key, '' if report.strip() else name, report, '')
        else:
            products=search_snapshot(snapshot, '' if report.strip() else name, report, '')
        # 부정확한 사진 제조사 OCR로 후보를 숨기지 않고, 화면에서 일치 여부를 별도 검증.
        products.sort(key=lambda p: (
            assess_product_match(p, name, maker, report).sufficient_for_claim_comparison,
            assess_product_match(p, name, maker, report).level == 'NAME_ONLY',
        ), reverse=True)
        st.session_state['products']=products
        st.session_state['lookup_time']=datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')
    except DataLookupError as exc:
        st.error(str(exc))

products=st.session_state.get('products',[])
if st.session_state.get('searched_terms') and st.session_state['searched_terms']!=(name.strip(),maker.strip(),report.strip()):
    products=[]
    st.warning('검색어가 변경됐습니다. 정확한 제품 연결을 위해 다시 조회하세요.')
selected=None
if products:
    st.success(f'{len(products)}개 후보를 찾았습니다. 아래에서 **실제 광고·포장과 같은 제품**인지 확인하세요.')
    choice=st.selectbox('확인할 제품',range(len(products)),
        format_func=lambda i:f'{products[i].product_name} | {products[i].maker} | {products[i].report_no}',
        key=f"selected_product_idx_{st.session_state['search_iteration']}")
    selected=products[choice]
    match=assess_product_match(selected,name,maker,report)
    if match.sufficient_for_claim_comparison:
        st.success(f'식별정보 비교: {match.label} — {match.details}')
    else:
        st.warning(f'식별정보 비교: {match.label} — {match.details}')
    st.markdown(f'**제품명:** {selected.product_name}')
    st.write(f'**업소명:** {selected.maker}')
    st.write(f'**품목제조번호:** {selected.report_no}')
    st.write(f'**제품 유형:** 건강기능식품 · {selected.category or "분류 세부정보 없음"}')
    st.markdown('**공식 기능성 원문**')
    st.info(selected.functionality or '공식 기능성 필드가 비어 있습니다. 확인 필요.')
    with st.expander('섭취 주의사항 / 데이터 정보'):
        st.write(selected.precautions or '섭취 주의사항 제공 정보 없음')
        st.write('기록 최종 수정일:',date_display(selected.last_updated))
        st.write('생산종료여부 필드:', selected.production_end or '미제공')
        st.caption('생산종료 표시는 현재 시판/판매 적법성 확인과 다릅니다.')
    st.caption(f'식약처 I0030 · {"실시간 호출" if selected.source=="live" else "2026-11-17 시연용 스냅샷"} · 조회 시각: {st.session_state.get("lookup_time","-")}')
    st.markdown(f'[식약처 공식 데이터 명세 열기]({I0030_DOC_URL})')
else:
    if st.session_state['searched']:
        st.warning('제품을 찾지 못했거나 조건이 일치하지 않습니다. **검색되지 않았다고 가짜·불법·일반식품인 것은 아닙니다.**')
    elif mode=='시연용 5건 스냅샷':
        st.caption('시연용 데이터는 업로드하신 5개 제품에 한해서만 검색됩니다.')

link_confirmed=False
if selected:
    match=assess_product_match(selected,name,maker,report)
    if match.sufficient_for_claim_comparison:
        link_confirmed=st.checkbox('포장지의 제품명과 제조사 또는 신고번호를 대조했으며, 광고 속 제품도 같은 제품임을 직접 확인했습니다.',key=f"confirmed_{st.session_state['search_iteration']}_{selected.report_no}")
    else:
        st.info('공식 기능성 부합 비교를 하려면 **제품명 + 제조업체** 또는 **정확한 신고번호**가 일치해야 합니다. 위 입력칸을 보완하고 다시 조회해 주세요. 치료·약 중단 위험 문구는 제품을 특정하지 않아도 경고합니다.')

st.subheader('③ 광고 문구 검증')
st.text_area('광고 효능 주장만 입력하거나 사진에서 자동 추출하세요',key='ad_text',height=130,
    placeholder='예: 이 홍삼스틱을 먹으면 고혈압이 완치되고 혈압약도 끊을 수 있습니다.')
def use_example_ad():
    st.session_state['ad_text']='이 홍삼스틱을 먹으면 고혈압이 완치되고 혈압약도 끊을 수 있습니다.'
st.button('🧪 가상 과장광고 예시 넣기',on_click=use_example_ad)

if st.button('🛡️ 광고 위험 표현 확인',type='primary',use_container_width=True):
    if not st.session_state['ad_text'].strip():
        st.warning('광고 문구를 먼저 입력해 주세요.')
    else:
        result=evaluate_ad(st.session_state['ad_text'],selected,link_confirmed)
        labels={'CAUTION':'🔴 광고 표현에 주의하세요',
                'NEEDS_CHECK':'🟠 추가 확인이 필요합니다',
                'POSSIBLY_MATCHED':'🟢 공식 기능성과 부합 가능'}
        if result['overall']=='CAUTION': st.error(labels['CAUTION'])
        elif result['overall']=='NEEDS_CHECK': st.warning(labels['NEEDS_CHECK'])
        else: st.success(labels['POSSIBLY_MATCHED'])
        voice_text=build_spoken_summary(result, selected, link_confirmed)
        if senior_mode:
            st.markdown('**🔊 아래 버튼을 누르면 결과를 한국어로 읽어드립니다.**')
            render_voice_player(voice_text)
            with st.container(border=True):
                st.markdown('### 한눈에 보는 결과')
                if result['overall']=='CAUTION':
                    st.error('광고에 위험한 표현이 있습니다. 구매나 약 중단을 결정하기 전에 확인하세요.')
                elif result['overall']=='NEEDS_CHECK':
                    st.warning('추가 확인이 필요합니다. 공식 제품정보와 완전히 연결되지 않았을 수 있습니다.')
                else:
                    st.success('확인된 제품의 공식 기능성과 광고 문구가 일부 부합합니다. 안전 보증은 아닙니다.')
                st.markdown('**약은 임의로 끊지 마세요.**')
            st.markdown('#### 자세한 판단 이유')
        for i,item in enumerate(result['claims'],1):
            with st.container(border=True):
                status={'CAUTION':'🔴 주의','NEEDS_CHECK':'🟠 확인 필요',
                        'POSSIBLY_MATCHED':'🟢 부합 가능'}[item['status']]
                st.markdown(f'**{i}. {status}**')
                st.write('광고 문장: ',item['claim'])
                for reason in item['reasons']:
                    st.write('•',reason)
        if not link_confirmed:
            st.info('광고와 제품의 동일성이 확인되지 않았으므로 **공식 기능성과 부합하는지**는 확정하지 않았습니다. 위험 표현 경고만 참고하세요.')
        if selected:
            with st.expander('판정 근거: 공식 기능성 원문'):
                st.write(selected.functionality or '공란')
                st.caption('원문은 식약처 I0030에서 조회한 항목이며 일부 광고 주장의 법적 판정 자료는 아닙니다.')
        st.markdown('**처방약을 광고만 보고 임의로 중단하지 마세요.** 의사·약사와 상담하세요.')
        st.caption(result['disclaimer'])
        st.caption('분류 방식: 보수적인 규칙 기반 문구 검토. 사진 글자 인식에 AI를 연결한 경우에도 최종 판정은 규칙으로 진행합니다.')

with st.expander('❓ 기능 범위와 개인정보 안내'):
    st.write('• 건강기능식품 I0030만 지원합니다. 의약품·일반식품 전체 조회는 아직 지원하지 않습니다.')
    st.write('• 조회되지 않으면 추가 확인 대상으로 처리합니다.')
    st.write('• 현재 문구 분류는 규칙 기반 예비 검토로, 맥락을 완벽하게 이해하거나 법적 판단을 내릴 수 없습니다.')
    st.write('• 제품 사진/광고 사진은 세션에서 처리하며 파일로 저장하지 않습니다. 사진 AI를 선택하면 Google Gemini API로 전송됩니다.')
    st.write('• API 키는 서버 환경변수·Streamlit 비밀 설정 또는 비밀번호 입력으로 관리합니다. 소스코드·공개 저장소에 올리지 마세요.')
    st.write('• 서비스 성능이나 사용자 효용은 아직 실사용자로 검증하지 않았습니다.')

st.caption('메디체크 AI MVP v1.6 · 사진 AI는 효능 주장 후보 추출만 담당하며, 공식 기록 연결과 판정은 보수적인 규칙으로 진행합니다.')
