# 메디체크 AI v1.7 — 어르신용 사진 한 장 검사

**사진 선택 → 검사하기 → Gemini OCR(1회) → 식약처 I0030 공식 조회(최대 1회) → 주의 표현 평가**를 한 화면에서 진행합니다. 제품을 확정할 수 없으면 안전하게 판단을 보류합니다.

## v1.7 주요 변경점

- 어르신 첫 화면을 사진 업로드 + `이 사진 검사하기` 중심으로 단순화
- 한 장에서 **제품명·제조사·신고번호·효능 주장** 추출
- 식약처 공식 제품 조회 자동 실행. 실패 시 과거 시연 데이터로 **자동 대체하지 않음**
- 품목제조번호 또는 제품명·제조사로 기록을 비교하며, 동일성 미확인 상태에서 '기능성 부합' 판정 금지
- 광고의 치료·완치·약 중단 표현은 제품 매칭과 독립적으로 주의 안내
- 검사 결과를 업로드 입력보다 화면 위에 표시, 한국어 음성 안내 유지
- 방문자의 인증키 입력·모델 선택·접속 코드 입력 칸 제거. 인증키는 Streamlit Cloud Secrets에서만 로드
- 사진 교체 시 기존 판정 초기화. 같은 사진 중복 검사 방지
- 1세션 12회 및 **한 서버 프로세스에서 최대 시간당 60회**의 가벼운 제한 적용(서버 재시작 시 초기화, 운영 전체 남용 방지 대책 아님)

## 구성

- `app.py` — Streamlit UI / 세션 흐름
- `workflow.py` — Gemini → 식약처 → 판정 단계 연결
- `vision.py` — Gemini 사진 인식 (v1.7 `single` 모드 추가)
- `rate_limit.py` — 기본 호출량 제한
- `engine.py` — I0030 제품 조회·광고 규칙 판정 (기존 유지)
- `match_utils.py` — 제품 동명이품·신고번호 대조 (기존 유지)
- `claim_filter.py` — 효능 주장만 필터링 (기존 유지)
- `senior_ui.py` — 큰 글씨 결과·한국어 음성 (기존 유지)
- `tests/` — 네트워크 모의 테스트

## PC 실행 (관리자)

`app.py`가 있는 폴더에서:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

최초 로컬 실행 시 실제 키는 **프로젝트에서 Git 무시되는** `.streamlit/secrets.toml`에 입력하거나 환경 변수로 설정합니다.

```toml
FOOD_SAFETY_API_KEY = "YOUR_FOOD_SAFETY_KEY"
GEMINI_API_KEY = "YOUR_GEMINI_KEY"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

`.streamlit/secrets.example.toml`에는 예시만 포함됩니다. **실제 키는 GitHub에 올리지 마세요.**

## 배포

기존 저장소 `sserip82-boop/medicheck-ai`에서 v1.6 버전을 백업한 뒤, v1.7 파일을 GitHub에 반영하세요. Streamlit Cloud는 커밋 변경을 감지하고 앱을 다시 실행합니다. **기존 Secrets는 재사용**하며 `APP_ACCESS_CODE`는 필요 없습니다.

초보자용 상세 절차: `DEPLOY_GUIDE_v1.7.md`.

## 테스트

```powershell
python -m pip install pytest
python -m pytest -q
```

- 2026-11-17: Python 컴파일 및 네트워크 모의 자동 테스트 **55개 통과**.
- 실제 Gemini + I0030 통합 호출, Streamlit 클라우드 실행 및 갤럭시 음성 재생은 **현재 환경에서 실행하지 못했으므로 배포 후 직접 확인해야 합니다**.

## 사용자 안내·제한

이 앱은 **건강기능식품 신고자료를 대조하는 시연용**입니다. 일반식품·의약품 전체를 판정하지 않으며, 질병 치료 효과·개별 복용 안전성·법적 위반 여부를 확정하지 않습니다. 사진의 개인정보를 가리고 올려야 하며, Gemini API 전송에 사용자 동의를 받습니다.

**공개 서비스 주의:** 앱 내부 호출 제한은 완전한 남용 방지 수단이 아닙니다. Google AI Studio의 실제 사용량·할당량·예산을 확인하고 필요시 외부 API 게이트웨이/전역 사용량 제한 기능을 추가하세요.
