# 메디체크 AI v1.6 — 스마트폰 배포 안내

## 먼저 알아둘 점

- `localhost:8501`은 **본인 컴퓨터에서만** 접근하는 주소입니다. 스마트폰에 링크를 보낼 수는 없습니다.
- 누구나 접근할 수 있는 웹 링크를 만들려면 **GitHub 저장소 + Streamlit Community Cloud 배포**가 필요합니다.
- GitHub에는 `.streamlit/secrets.toml`이나 API 키가 포함된 파일·스크린샷을 절대 올리지 마세요.
- Streamlit Community Cloud의 Secrets에 API 키를 등록하면 서버가 호출하므로 일반 방문자는 키를 볼 필요가 없습니다. v1.6은 서버 키를 입력창 기본값으로 **표시하지 않습니다**.
- 테스트 전에는 `APP_ACCESS_CODE`도 설정해 링크를 가진 누구나 API를 호출하는 일을 막으세요. 간단한 접속 코드 기능이며 정식 회원인증을 대신하지 않습니다.

## 1. 로컬에서 v1.6 시험

1. v1.5의 PowerShell 창에서 `Ctrl+C`로 종료합니다.
2. 새 v1.6 ZIP 압축을 풀어 `app.py`와 `requirements.txt`가 보이는 폴더로 들어갑니다.
3. 탐색기 주소창에 `powershell` 입력 후 Enter.
4. 차례로 실행:
   ```powershell
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```
5. 결과 판정까지 진행한 후 **🔊 결과 듣기** 버튼을 눌러 한국어 음성을 확인합니다. 글씨가 너무 크면 왼쪽의 ‘어르신용 큰 글씨’를 끕니다.
6. PC Chrome은 보통 한국어 음성을 읽을 수 있지만, 일부 스마트폰 브라우저·무음 모드·한국어 TTS 미설치 환경에서는 안 될 수 있습니다. 결과 글자 표시는 항상 유지됩니다.

## 2. GitHub에 코드 올리기 (Windows 초보자)

1. https://github.com 에 로그인하고 `New repository`를 눌러 이름을 `medicheck-ai`로 지정합니다.
2. 공개(Public) 또는 비공개(Private)를 선택합니다. 공개 프로젝트는 누구나 코드를 볼 수 있습니다. Streamlit Cloud 계정과 공유 설정도 확인하세요.
3. 저장소의 `Add file` → `Upload files`를 이용합니다. **압축파일 자체가 아니라 ZIP을 풀어 나온 코드 파일**을 올리세요. `app.py`, `engine.py`, `vision.py`, `claim_filter.py`, `match_utils.py`, `senior_ui.py`, `demo_i0030.json`, `requirements.txt` 등입니다. 예시 비밀설정만 올려도 되지만 실제 비밀설정 파일은 제외합니다.
4. `.streamlit/config.toml`은 선택사항입니다. 처음에는 없어도 Streamlit이 실행됩니다.
5. `Commit changes`를 눌러 저장합니다.

## 3. Streamlit Community Cloud 배포

1. https://share.streamlit.io/ 에 접속해 GitHub 계정으로 로그인합니다.
2. `Create app` → `Yup, I have an app` 선택.
3. 방금 생성한 GitHub 저장소 선택, `Branch: main`, `Main file path: app.py`로 지정.
4. `Advanced settings` → `Secrets`에 다음을 입력하되, **실제 키는 본인 화면에만 입력**하세요.
   ```toml
   FOOD_SAFETY_API_KEY = "식약처에서_발급받은_키"
   GEMINI_API_KEY = "Google_AI_Studio_API_키"
   GEMINI_MODEL = "gemini-3.5-flash-lite"
   APP_ACCESS_CODE = "직접_정한_긴_접속_코드"
   ```
5. `Deploy`를 눌러 배포합니다. 성공하면 실제 `https://...streamlit.app` 형태의 주소가 발급됩니다.
6. 휴대폰에서 해당 URL을 열고 `APP_ACCESS_CODE`에 등록한 시연 접속 코드를 입력합니다. 사진 업로드 → Gemini 글자 읽기 → 식약처 조회 → 제품 연결 확인 → 광고 결과 읽기 순서로 시험합니다.

## 4. 배포 후 필수 확인

- [ ] GitHub 저장소에 실제 인증키·API 키가 노출되지 않았는가?
- [ ] 스마트폰에서 주소가 열리는가?
- [ ] 시연 접속 코드 없이 앱 내용에 접근할 수 없는가?
- [ ] 모바일 데이터(와이파이가 아닌)에서도 열리는가?
- [ ] 사진을 업로드하고 자동 효능 추출이 되는가?
- [ ] 공식 조회 실패 시 안전한 '확인 필요' 안내가 되는가?
- [ ] 큰 글씨와 한국어 음성 읽기가 작동하는가?
- [ ] 제품명만 같으면 동일성 확인을 보류하는가?

## 5. 주의

- 광고 표현을 단순 분류하는 시제품이며, 의료나 광고 규제 준수에 대한 공식 판정 시스템이 아닙니다.
- Google Gemini 이미지 인식은 외부 전송 동의를 받은 후에만 사용합니다. 얼굴·주소·전화번호 등이 포함된 사진은 업로드하지 마세요.
- 데모 링크를 공개할수록 API 사용량 및 요금이 증가할 수 있습니다. 테스트가 끝나면 Streamlit 비밀설정을 변경하거나 공유 범위를 제한하세요.
- Streamlit Cloud 앱은 외부 서비스 정책과 할당량, 네트워크 환경에 따라 오류가 날 수 있습니다.

공식 배포 설명:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
