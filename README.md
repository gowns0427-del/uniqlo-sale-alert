# 유니클로 세일 알림판

유니클로 한국의 **기간한정가격**, **가격인하** 상품을 1시간마다 모아서 보여주는 오픈소스 HTML 대시보드입니다.
서버 없이 GitHub Actions와 GitHub Pages만으로 돌아갑니다.

- 지금 진행 중인 기간한정가격 회차, 기간, 남은 시간
- 기간한정가격 상품 목록 (WOMEN / MEN / KIDS / BABY 필터)
- 최근에 가격이 내려간 상품
- 기간한정가격 상품이 80개 이상이면 **대형 세일(감사제 가능성)** 표시
- 지금까지 감지한 세일 회차 기록

## 동작 방식

```
GitHub Actions (매시간)
  └─ collector/collect.py ── 유니클로 상품 검색 API 호출
        └─ docs/data.json 저장·커밋
              └─ GitHub Pages ── docs/index.html 이 data.json 을 읽어 표시
```

유니클로 API는 브라우저에서 다른 사이트가 직접 호출하는 것을 허용하지 않아서(CORS), 수집은 GitHub Actions가 맡고
HTML은 저장된 `data.json`만 읽습니다. 수집기는 파이썬 표준 라이브러리만 사용합니다.

## 내 GitHub에 배포하기

1. 이 저장소를 Fork 하거나 새 저장소에 올립니다.
2. **Settings → Pages → Build and deployment → Source** 를 **GitHub Actions** 로 바꿉니다.
3. **Actions** 탭에서 워크플로를 활성화하고 `세일 정보 업데이트` 를 **Run workflow** 로 한 번 실행합니다.
4. `https://<내 아이디>.github.io/<저장소 이름>/` 에서 알림판을 엽니다.

이후에는 매시간 자동으로 갱신됩니다.

> GitHub는 60일 동안 저장소에 활동이 없으면 예약 워크플로를 멈춥니다. 수집 결과가 바뀔 때마다 커밋이 생기므로 보통은 문제없지만,
> 멈췄다면 Actions 탭에서 다시 켜 주세요.

## 내 컴퓨터에서 실행하기

```bash
python collector/collect.py
```

```bash
python -m http.server 8000 --directory docs
```

브라우저에서 http://localhost:8000 을 엽니다. (`index.html` 파일을 바로 열면 `data.json` 을 읽지 못합니다.)

## 설정

`collector/collect.py` 위쪽 상수로 조정합니다.

| 상수 | 기본값 | 설명 |
| --- | --- | --- |
| `BIG_SALE_THRESHOLD` | `80` | 기간한정가격 상품이 이 수 이상이면 대형 세일로 표시 |
| `DISCOUNT_PRODUCT_LIMIT` | `60` | 대시보드에 보여줄 가격인하 상품 수 |
| `HISTORY_LIMIT` | `100` | 보관할 세일 회차 기록 수 |

## 주의

- 유니클로 공식 사이트가 쓰는 비공개 API를 사용합니다. 사이트 구조가 바뀌면 동작하지 않을 수 있습니다.
- 요청은 한 시간에 몇 번뿐이지만, 수집 주기를 너무 짧게 바꾸지 말아 주세요.
- 이 프로젝트는 유니클로(주식회사 패스트리테일링)와 관련이 없는 비공식 프로젝트입니다.

## 라이선스

MIT
