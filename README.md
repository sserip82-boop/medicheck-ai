# 메디체크 AI v1.6 — 어르신 큰 글씨·한국어 음성·스마트폰 배포 준비

기존 v1.5의 **Google Gemini 이미지 인식**, **식약처 I0030 실시간 제품 검색**, **효능 주장 필터**, **제품 식별정보 대조**, **광고 위험 표현 규칙 판정**을 유지합니다.

## v1.6 추가 사항

- 기본 활성화된 **어르신용 큰 글씨**: 모바일 반응형 서체, 높이가 큰 버튼, 짧은 결과 요약
- 검증 결과의 **🔊 결과 듣기 / ■ 읽기 중지**: 사용 중인 스마트폰·PC의 브라우저 한국어 TTS 사용; 별도 음성 API 키나 음성파일 전송 불필요
- **서버 API 키 화면 노출 방지**: `st.secrets`/환경변수에 저장한 키를 비밀번호 입력칸의 초기값으로 표시하지 않음
- **선택적 시연용 접속 코드**: `APP_ACCESS_CODE`를 지정하면 코드 입력 후 앱 사용 가능. 정식 로그인/권한관리 수준의 보안을 제공하지는 않습니다.
- 배포용 `DEPLOY_GUIDE.md`, `.streamlit/secrets.example.toml`, `.gitignore` 포함

## 로컬 실행

`app.py`가 있는 폴더에서:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 스마트폰 배포

**[DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)**를 따라 GitHub에 비밀키를 제외한 코드를 올리고 Streamlit Community Cloud에서 GitHub 저장소를 연결하세요. 서비스가 배포되어야 휴대폰으로 열 수 있는 공개 URL이 생깁니다.

## 자동 테스트

```powershell
python -m pip install pytest
python -m pytest -q
```

기존 v1.5 외부 API 연동은 사용자 PC에서 동작을 확인했습니다. v1.6의 **한국어 TTS는 기기별로 직접 눌러 확인해야** 합니다. 이 환경에서는 실제 마이크·스피커 및 클라우드 배포를 직접 검증할 수 없습니다.
