"""메디체크 AI v1.7: 어르신용 사진 한 장 검사 웹앱.

한 번 검사 버튼으로 OCR -> 식약처 I0030 조회 -> 예비 위험 판정.
공식 기능성 부합 판정은 포장·광고의 동일성 확인 후에만 허용.
"""
from __future__ import annotations
import hashlib
import os
from datetime import datetime
from pathlib import Path
from time import monotonic
from rate_limit import PUBLIC_LIMITER

import streamlit as st

from engine import I0030_DOC_URL, date_display
from match_utils import assess_product_match
from senior_ui import build_spoken_summary, render_voice_player
from vision import DEFAULT_GEMINI_MODEL, ALLOWED_GEMINI_MODELS
from workflow import scan_one_photo, lookup_products, selected_result, recommended_candidate, candidate_matches

st.set_page_config(page_title='메디체크 AI | 사진으로 확인', page_icon='🛡️',
                   layout='centered', initial_sidebar_state='collapsed')

st.markdown('''<style>
html,body,[class*="css"] {font-family:"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.block-container {max-width:760px; padding:1rem 1rem 3rem!important}
[data-testid="stSidebar"] {font-size:.9rem}
.stButton>button,.stFormSubmitButton>button {
 min-height:64px; width:100%; border-radius:16px; font-size:1.22rem; font-weight:750;
}
[data-testid="stFileUploader"] {border-radius:16px}
[data-testid="stAlert"] {font-size:1.12rem;line-height:1.7;border-radius:14px}
input,textarea{font-size:1.15rem!important}
.hero-title{font-size:2rem;line-height:1.45;font-weight:850;margin:0 0 10px}
.hero-description{font-size:1.26rem;line-height:1.7;margin:0 0 12px}
.result-title{font-size:1.68rem;line-height:1.45;font-weight:850;margin:.25rem 0 .7rem}
.result-help{font-size:1.19rem;line-height:1.75}
@media(max-width:650px){
 .hero-title{font-size:1.68rem}
 .hero-description{font-size:1.13rem}
 .result-title{font-size:1.5rem}
 .stButton>button,.stFormSubmitButton>button {min-height:66px}
}
</style>''',unsafe_allow_html=True)


def secret(key: str) -> str:
    try:
        configured = st.secrets.get(key, '')
    except Exception:
        configured = ''
    return str(configured or os.environ.get(key,'') or '').strip()


food_key = secret('FOOD_SAFETY_API_KEY')
gemini_key = secret('GEMINI_API_KEY')
gemini_model = secret('GEMINI_MODEL') or DEFAULT_GEMINI_MODEL
if gemini_model not in ALLOWED_GEMINI_MODELS:
    gemini_model = DEFAULT_GEMINI_MODEL

for key, default in {
    'photo_fingerprint':None, 'scan_report':None, 'last_scanned_hash':None,
    'last_scan_at':-1., 'scan_calls':0, 'edit_revision':0,
    'confirmed_record':None, 'show_alternatives':False, 'rejected_candidate':None,
}.items():
    if key not in st.session_state:
        st.session_state[key]=default

with st.sidebar:
    st.header('🔎 서비스 안내')
    st.write('건강기능식품 광고 문구를 공식 신고정보와 비교하는 학습·시연용 앱입니다.')
    st.caption('사진 인식: Google Gemini · 제품정보: 식약처 I0030')
    if gemini_key:
        st.success('사진 인식 준비됨')
    else:
        st.warning('사진 인식 서버 설정 확인 필요')
    if food_key:
        st.success('식약처 공식 조회 준비됨')
    else:
        st.warning('식약처 공식 조회 서버 설정 확인 필요')
    st.markdown(f'[식약처 데이터 출처]({I0030_DOC_URL})')
    st.caption('방문자는 API 키를 입력할 필요가 없습니다. 키는 Streamlit Cloud Secrets에만 보관합니다.')

st.title('🛡️ 메디체크 AI')
st.markdown('<div class="hero-title">건강식품 광고, 믿어도 될까요?</div>',unsafe_allow_html=True)
st.markdown('<div class="hero-description">사진 한 장을 올리고 <b>검사하기</b>를 누르세요.</div>',unsafe_allow_html=True)

# Place a result container ABOVE upload widget for elderly users on long mobile pages.
result_slot=st.container()

st.subheader('① 사진 올리기')
st.caption('광고 화면이나 제품 포장 사진을 선택하세요. 글자가 잘 보이게 찍어 주세요.')
photo=st.file_uploader('사진 촬영·선택',type=['jpg','jpeg','png','webp'],
                       accept_multiple_files=False,label_visibility='visible')

fingerprint=hashlib.sha256(photo.getvalue()).hexdigest() if photo else None
if st.session_state['photo_fingerprint']!=fingerprint:
    st.session_state['photo_fingerprint']=fingerprint
    st.session_state['scan_report']=None
    st.session_state['last_scanned_hash']=None
    st.session_state['edit_revision']+=1
    st.session_state['confirmed_record']=None
    st.session_state['show_alternatives']=False
    st.session_state['rejected_candidate']=None

if photo:
    st.caption(f'선택한 사진: {photo.name} · {len(photo.getvalue())/1024/1024:.1f}MB')
consent=st.checkbox('사진을 Google Gemini AI에 보내 글자를 읽는 데 동의합니다.',value=False)
st.caption('사진을 앱의 파일로 영구 저장하지 않습니다. 전화번호·주소·얼굴 등 개인정보가 있다면 가리고 올려주세요.')

if not gemini_key:
    st.warning('사진 인식 서버 설정이 준비되지 않았습니다. 운영자가 Streamlit Secrets의 GEMINI_API_KEY를 확인해야 합니다.')

clicked=st.button('🔍 이 사진 검사하기', type='primary', use_container_width=True,
                  disabled=not (photo and consent and gemini_key))
if clicked:
    now=monotonic()
    if fingerprint==st.session_state['last_scanned_hash'] and st.session_state['scan_report'] is not None:
        st.info('같은 사진의 결과가 위에 있습니다. 다시 비용을 발생시키지 않았습니다.')
    elif st.session_state['scan_calls']>=12:
        st.warning('한 번의 접속에서 너무 많은 검사를 요청했습니다. 잠시 사용을 멈추고 다시 접속해 주세요.')
    elif now-st.session_state['last_scan_at']<5:
        st.info('연속 분석을 방지하고 있습니다. 잠시 후 다시 검사해 주세요.')
    elif not PUBLIC_LIMITER.try_consume():
        st.warning('현재 사진 분석 요청이 많습니다. 사용량 보호를 위해 잠시 사진 분석을 제한합니다.')
    else:
        st.session_state['scan_calls']+=1
        st.session_state['last_scan_at']=now
        try:
            with st.spinner('사진을 읽고 식약처 공식 정보를 확인하고 있어요...'):
                report=scan_one_photo(photo.getvalue(),gemini_key,food_key,model=gemini_model)
            st.session_state['scan_report']=report
            st.session_state['last_scanned_hash']=fingerprint
        except RuntimeError as exc:
            st.error(f'사진 인식에 실패했어요. {exc}')
        except Exception:
            st.error('사진 검사 중 오류가 발생했습니다. 다시 시도하거나 글자가 선명한 사진을 사용해 주세요.')


def render_report(report):
    st.divider()
    st.markdown('<div class="result-title">② 검사 결과</div>',unsafe_allow_html=True)

    if not report.claim_candidates:
        st.warning('사진에서 건강 효능을 약속하는 문장을 찾지 못했습니다. 광고가 아니거나 글자가 흐릴 수 있습니다.')
    else:
        st.caption(f'사진에서 확인한 효능 주장 {len(report.claim_candidates)}개')

    products=report.products
    selected=None
    suggested=recommended_candidate(report)
    if suggested and st.session_state.get('rejected_candidate')==suggested.report_no:
        suggested=None

    if report.manufacturer_evidence:
        st.caption('사진에서 찾은 업체 표시: '+report.manufacturer_evidence)
    elif report.seller_evidence:
        st.info('사진에서 판매원만 확인했습니다: '+report.seller_evidence+'\n\n판매원은 제조사와 다를 수 있어 업체명을 다시 확인해야 합니다.')

    if products:
        if suggested is not None:
            selected=suggested
            st.info('사진에 적힌 업체명과 제품명(또는 신고번호)에 맞는 **유력한 공식 기록**을 찾았어요. 같은 제품인지는 직접 확인해 주세요.')
            st.markdown('#### 사진과 같은 제품인가요?')
            with st.container(border=True):
                st.markdown('**'+suggested.product_name+'**')
                st.write('공식 제조업체: '+suggested.maker)
                st.caption('품목제조번호: '+suggested.report_no)
                if st.button('✅ 네, 포장과 같은 제품이에요',key='agree_recommend',use_container_width=True):
                    st.session_state['confirmed_record']=suggested.report_no
                if st.button('아니에요 · 다른 제품 찾기',key='reject_recommend',use_container_width=True):
                    st.session_state['confirmed_record']=None
                    st.session_state['rejected_candidate']=suggested.report_no
                    st.session_state['show_alternatives']=True
                    st.rerun()
        elif len(products)==1:
            selected=products[0]
            st.info('공식 조회 후보: '+selected.product_name+' · '+selected.maker+' (동일 제품 여부는 미확인)')
        else:
            st.info(f'비슷한 이름의 식약처 공식 기록 {len(products)}건이 검색됐어요. **제품명을 기준으로 임의 확정하지 않습니다.**')
    elif report.lookup_error:
        st.info('공식 제품 확인: '+report.lookup_error)
    else:
        st.info('식약처 공식 제품을 찾지 못했어요. 검색되지 않았다고 가짜 제품이라는 뜻은 아닙니다.')

    # Simple, source-aware fallback. Seller-only text must not be used as manufacturer proof.
    if products and not report.manufacturer_verified and not report.report_no:
        st.markdown('#### 포장에 적힌 업체를 확인해 주세요')
        st.caption('제품명만으로는 같은 제품인지 알 수 없어요. 아래는 사진에 실제로 적힌 내용을 입력하는 칸입니다.')
        with st.form(f'company_quick_{st.session_state["edit_revision"]}'):
            company_input=st.text_input('포장에 적힌 업체명',value=report.seller or '',placeholder='예: (주)씨스팡')
            company_role=st.radio('사진에 어떤 이름으로 적혀 있나요?',
                ['제조원 · 제조업체','제조 및 판매원','판매원만 표시'],horizontal=False,index=None)
            company_submit=st.form_submit_button('이 업체명으로 제품 다시 확인',use_container_width=True)
        if company_submit:
            if not company_input.strip() or not company_role:
                st.warning('업체명과 사진에 표시된 역할을 모두 확인해 주세요.')
            else:
                st.session_state['confirmed_record']=None
                st.session_state['rejected_candidate']=None
                st.session_state['show_alternatives']=False
                company=company_input.strip()
                if company_role=='판매원만 표시':
                    report.seller=company
                    report.seller_evidence='사용자가 사진의 판매원 표기를 확인하여 입력함'
                    report.manufacturer=''
                    report.manufacturer_verified=False
                    report.company_role='seller'
                else:
                    report.manufacturer=company
                    report.manufacturer_verified=True
                    report.manufacturer_evidence='사용자가 포장에 표시된 '+company_role+'을 직접 확인하여 입력함'
                    report.company_role='combined' if company_role=='제조 및 판매원' else 'manufacturer'
                st.session_state['scan_report']=report
                st.session_state['edit_revision']+=1
                # No extra food API call: current candidate list can be matched locally.
                st.rerun()

    if len(products)>1 and (suggested is None or st.session_state['show_alternatives']):
        with st.expander('다른 공식 검색 결과에서 직접 선택하기',expanded=suggested is None):
            choice=st.selectbox('포장과 같은 제품이 있나요?',
                options=list(range(len(products))),index=None,placeholder='다른 제품 선택',
                format_func=lambda i:f'{products[i].product_name} | {products[i].maker} | {products[i].report_no}',
                key=f'candidate_v171_{st.session_state["edit_revision"]}')
            if choice is not None:
                selected=products[choice]

    confirmed=False
    match=None
    if selected:
        match=candidate_matches(report, selected)
        if match.sufficient_for_claim_comparison:
            if suggested is None or selected.report_no!=suggested.report_no:
                st.caption('공식 기록과 사진 속 업체정보 비교: '+match.label)
                if st.button('✅ 네, 선택한 공식 기록이 사진 속 제품과 같아요',
                             key=f'confirm_alt_{st.session_state["edit_revision"]}_{selected.report_no}',
                             use_container_width=True):
                    st.session_state['confirmed_record']=selected.report_no
            confirmed=st.session_state.get('confirmed_record')==selected.report_no
            if confirmed:
                st.success('제품명과 업체정보를 대조하고 사용자가 동일한 제품임을 확인했어요.')
            else:
                st.warning('이 제품인지 아직 확인하지 않았어요. 포장 정보를 직접 대조해 주세요.')
        else:
            st.warning('제품 확인이 더 필요합니다. '+match.details)
    if report.claim_candidates:
        result=selected_result(report,selected,confirmed)
        if result['overall']=='CAUTION':
            st.error('🔴 광고 표현에 주의하세요. 위험한 효능 주장이 포함되어 있습니다.')
        elif result['overall']=='POSSIBLY_MATCHED':
            st.success('🟢 공식 기능성 문구와 일부 부합합니다. 안전성·광고 적법성 보증은 아닙니다.')
        else:
            st.warning('🟠 추가 확인이 필요합니다. 아직 확정적인 결론을 내릴 수 없습니다.')
        for item in result['claims'][:5]:
            st.markdown(f'**“{item["claim"]}”**')
            for reason in item['reasons'][:2]:
                st.write('•',reason)
        st.markdown('### 🔊 결과를 소리로 듣기')
        render_voice_player(build_spoken_summary(result,selected, bool(confirmed and match and match.sufficient_for_claim_comparison)))
        st.caption('의료·법률적 최종 판정이 아닙니다. 광고만 보고 처방약을 중단하지 마세요.')
    else:
        st.caption('공식 기록 확인과 별개로, 검증할 광고 효능 주장이 없으면 위험 판정은 수행하지 않습니다.')

    if selected:
        with st.expander('식약처 공식 제품정보 자세히 보기'):
            st.write('제품명:',selected.product_name)
            st.write('제조업체:',selected.maker)
            st.write('품목제조번호:',selected.report_no)
            st.write('공식 기능성 원문:',selected.functionality or '제공되지 않음')
            st.write('섭취 시 주의사항:',selected.precautions or '제공되지 않음')
            st.write('기록 수정일:',date_display(selected.last_updated))
            st.caption('식약처 I0030 '+('실시간 조회' if selected.source=='live' else '시연용 자료'))

    with st.expander('글자를 잘못 읽었나요? 수정하고 다시 조회하기'):
        rev=st.session_state['edit_revision']
        with st.form(f'fix_ocr_{rev}'):
            name=st.text_input('제품명',value=report.product_name)
            maker=st.text_input('제조사',value=report.manufacturer)
            number=st.text_input('품목제조번호',value=report.report_no)
            claims=st.text_area('검증할 효능 문구 (한 줄에 하나)',value=report.claims_text,height=110)
            submitted=st.form_submit_button('수정한 정보로 다시 확인')
        if submitted:
            report.product_name=name.strip()
            report.manufacturer=maker.strip()
            report.manufacturer_verified=bool(maker.strip())
            report.company_role='user_confirmed' if maker.strip() else 'unknown'
            report.manufacturer_evidence='사용자가 사진의 제조원 표기를 확인하여 수정함' if maker.strip() else ''
            report.seller=''
            report.seller_evidence=''
            report.combined_company=''
            report.report_no=number.strip()
            report.claim_candidates=[x.strip() for x in claims.splitlines() if x.strip()][:12]
            lookup_products(report,food_key)
            st.session_state['scan_report']=report
            st.session_state['edit_revision']+=1
            st.session_state['confirmed_record']=None
            st.session_state['show_alternatives']=False
            st.session_state['rejected_candidate']=None
            st.rerun()
        with st.expander('사진에서 읽은 전체 글자 보기'):
            st.text_area('OCR 원문',value=report.full_text,height=160,disabled=True)


report=st.session_state.get('scan_report')
if report is not None:
    with result_slot:
        render_report(report)

with st.expander('서비스 이용 안내 / 분석 결과의 한계'):
    st.write('• 건강기능식품 I0030만 조회합니다. 의약품·일반식품 전체 조회는 지원하지 않습니다.')
    st.write('• AI는 사진에서 주장 후보를 추출할 뿐, 질병 치료나 의학적 효능을 확정하지 않습니다.')
    st.write('• 공식 제품을 잘못 연결하지 않도록 제조사·신고번호·제품명 일치 여부를 확인합니다.')
    st.write('• 사진은 Gemini API로 전송됩니다. 본 앱은 업로드한 사진을 영구 파일로 저장하지 않습니다.')
    st.write('• 실시간 조회 실패 시 오래된 시연용 데이터로 자동 전환하지 않습니다.')
    st.write('• 세션별·서버 프로세스별 간단한 요청 제한이 있지만 완전한 남용 방지 기능은 아닙니다. Google API 요금·할당량도 제한해야 합니다.')

st.caption('메디체크 AI MVP v1.7.1 · 카카오 AI 루키캠프 학생 프로젝트 · 결과는 참고용입니다.')
