# 매칭

LLM(또는 stub)이 뽑은 `interests` / `help_fields` / `situation` 과  
`data/mentors.cleaned.csv`(Syntitan 정리본) 선배를 비교해 점수를 매깁니다.

후보가 없으면 빈 배열을 반환합니다.
