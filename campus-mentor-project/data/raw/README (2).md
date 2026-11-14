# 원본 선배 데이터 (Syntitan 전)

여기에 수집한 원본 CSV/엑셀을 둡니다. **GitHub에는 실제 개인정보를 올리지 마세요.**

## Syntitan 정리 흐름

1. 원본 파일을 Syntitan에 업로드
2. Ready for Raw Data 등으로 빈칸·중복·모호한 열을 정리
3. 정리된 파일을 내려받아 `../mentors.cleaned.csv` 로 저장
4. 백엔드 실행 중이면 `POST /api/mentors/reload` 로 다시 로드

정리 후 CSV 권장 열: `mentor_id,display_name,major,experiences,help_topics,bio`  
`experiences` / `help_topics` 는 `|` 로 여러 값 구분.
