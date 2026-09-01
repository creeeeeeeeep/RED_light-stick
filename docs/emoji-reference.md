# 치지직 이모티콘 구조 (emoji-packs 응답 분석)

실제 `emoji-packs` API 요청/응답을 뜯어서 정리한 것. 2026-08-18 기준.

---

## 0. 엔드포인트

```
GET https://api.chzzk.naver.com/service/v1/channels/{channelId}/emoji-packs
```

`{channelId}` 는 시청 중인 채널 ID. 채팅 iframe URL에서 뽑을 수 있다.

```
https://chzzk.naver.com/iframe/live/{channelId}/chat?theme=light
```

### 호출 조건

| 항목 | 값 |
|---|---|
| 쿠키 | 필요 (`credentials: 'include'`) |
| `Origin` | `https://chzzk.naver.com` 이어야 함 |
| `Front-Client-Platform-Type` | `PC` |
| `Front-Client-Product-Type` | `web` |
| `Deviceid` | 클라이언트가 생성해 보관하는 UUID |

응답 헤더가 `Access-Control-Allow-Origin: https://chzzk.naver.com` +
`Access-Control-Allow-Credentials: true` 로 **오리진이 고정**돼 있다.

> **확장 설계에 미치는 영향:** 이 호출은 반드시 **페이지 컨텍스트**에서 나가야 한다.
> 백그라운드 서비스 워커에서 부르면 오리진이 안 맞아 CORS로 막힌다.
> 콘텐츠 스크립트를 채팅 iframe(`chzzk.naver.com/iframe/*`)에 주입하고
> 거기서 호출할 것. manifest 에 `all_frames: true` 필요.
>
> 커스텀 헤더 3개 때문에 preflight(OPTIONS)가 먼저 나간다. 헤더를 빠뜨리면
> 응답이 달라지거나 거부될 수 있으니 그대로 복제할 것.

**주의:** 이 요청의 Cookie 헤더에는 네이버 세션 토큰(`NID_AUT`, `NID_SES`)이 들어간다.
캡처를 외부에 공유할 때 절대 포함시키지 말 것.

### 응답 범위

시청 중인 채널과 무관하게 **그 계정이 보유한 구독 이모티콘 전체**가 내려온다.
(예: 채널 `3036abc...` 를 보는 중에도 구독 중인 다른 4개 채널의 팩이 전부 포함됨)

---

## 1. 응답 구조

```
content
├── emojiPacks[]              # 누구나 쓸 수 있는 기본 이모티콘
│   ├── dp_1   "CHZZK 이모티콘"   → emojiId: d_1 ~ d_280
│   ├── lckp_1 "LCK 이모티콘"     → emojiId: lck_1 ~ lck_38
│   └── mlb_1  "MLB 이모티콘"     → emojiId: mlb_1 ~ mlb_131
├── cheatKeyEmojiPacks[]      # (비어 있음)
└── subscriptionEmojiPacks[]  # 구독 관련
    ├── sdp_1 "CHZZK 구독티콘"  emojiType: SUBSCRIBER_DEFAULT
    │                          → emojiId: sd_1 ~ sd_10
    └── <채널ID> "<채널명>"      emojiType: SUBSCRIPTION_CHANNEL
                               → emojiId: 채널접두사 + 이름
```

각 이모티콘 항목은 단 두 필드다.

```json
{ "emojiId": "redredLight", "imageUrl": "https://nng-phinf.pstatic.net/..." }
```

**`emojiId` 가 곧 채팅에서 쓰는 키다.** 채팅 본문에는 `{:redredLight:}` 형태로 들어간다.

---

## 2. 가장 중요한 발견 — 구독 여부를 여기서 알 수 있다

`subscriptionEmojiPacks` 의 각 팩에 잠금 플래그가 있다.

| 필드 | 의미 |
|---|---|
| `emojiPackLocked` | `true` = 이 채널 구독 안 함 (티어1도 못 씀) |
| `emojiTier2Locked` | `true` = 티어2 미구독 |
| `tier1Emojis[]` | 티어1 구독자가 쓸 수 있는 목록 |
| `tier2Emojis[]` | 티어2 구독자만 쓸 수 있는 목록 |
| `tier1BrandName` | 티어1 등급 이름 (예: "크라운") |
| `tier2BrandName` | 티어2 등급 이름 (예: "로얄크라운") |

**별도의 구독 확인 API가 필요 없다.** 확장이 이 응답 하나만 읽으면
"이 팬이 지금 쓸 수 있는 이모티콘 전체 목록"이 그대로 나온다.

응원봉이 보낼 이모티콘을 고를 때 이 플래그를 보고 자동으로 걸러내면,
비구독자에게는 기본 이모티콘(`d_*`)으로 폴백시킬 수 있다.

`emojiPackId` 는 `SUBSCRIPTION_CHANNEL` 팩의 경우 **채널 ID** 와 같다.

---

## 3. RED레드 채널 (`a96cea2d2c39cec636ba8170c66a0510`)

등급 이름이 **크라운 / 로얄크라운**이고, 응원봉·왕관 관련 이모티콘이 이미 갖춰져 있다.
`CROWN_v12` 3D 모델과 정확히 맞아떨어진다.

### 응원봉 / 왕관 관련 (티어1 — 크라운)

| emojiId | 형식 | 비고 |
|---|---|---|
| `redredLight` | gif | 응원봉 흔드는 애니메이션 |
| `redredLight5` | gif | 응원봉 |
| `redredLightstick1` | png | 응원봉 |
| `redredLight1` | png | 응원봉 |
| `redredCrownlight` | png | 왕관 + 불빛 |
| `redredCrownheart` | gif | 왕관 하트 |
| `redredGoldclap` | png | 박수 |
| `redredHands` | png | 손 |
| `redredWoohyo` | gif | 환호 |
| `redredMinidance1` / `2` | gif | 춤 |

### 티어2 전용 (로얄크라운)

`redredLightsp1`, `redredGoldclap2`, `redredRedclap`,
`redredRedtaker1`, `redredRedtaker2`,
`redredRe`, `redredHa`, `redredBa`, `redredGon`, `redredDyu`

> 티어2 이모티콘을 쓰면 로얄크라운 구독자만 봉이 완전 동작한다.
> 티어1 이모티콘으로 가는 편이 대상이 넓다.

---

## 4. 모션 → 이모티콘 매핑 (제안)

펌웨어가 인식하는 3가지 모션에 대응시킨 초안.

| 모션 | 이모티콘 | 이유 |
|---|---|---|
| `SWAY_LR` 좌우 흔들기 | `redredLight` | 응원봉 흔드는 gif — 동작이 그대로 대응 |
| `PUMP_UD` 위아래 찍기 | `redredCrownlight` | 위로 치켜드는 동작 = 왕관 |
| `VIGOROUS` 격하게 | `redredWoohyo` 또는 `redredCrownheart` | 최고조 환호 |

비구독자 폴백은 기본 팩에서 고르면 된다 (`d_*`).

---

## 5. 채팅 WebSocket 전송 프레임 (실측)

`ws-capture.js` 로 잡은 실제 이모티콘 전송 프레임. 민감값은 가림.

```json
{
  "ver": "3",
  "cmd": 3101,
  "svcid": "game",
  "cid": "N2gaBX",
  "sid": "<세션 ID>",
  "bdy": {
    "msg": "{:redredLight:}",
    "msgTypeCode": 1,
    "extras": "<아래 객체를 JSON 문자열로 직렬화한 것>",
    "msgTime": 1786991193640
  },
  "tid": 3
}
```

`bdy.extras` 를 풀면:

```json
{
  "chatType": "STREAMING",
  "osType": "PC",
  "extraToken": "<세션 토큰>",
  "streamingChannelId": "3036abc221a6c4fa955ec08b4dddee96",
  "emojis": {
    "redredLight": "https://nng-phinf.pstatic.net/glive/subscription/emoji/a96cea.../1/redredLight_1728386596692.gif?type=f60_60"
  }
}
```

### 필드 정리

| 필드 | 성격 | 비고 |
|---|---|---|
| `cmd` | 고정 | `3101` = 채팅 전송. `0` 은 하트비트 |
| `ver` / `svcid` | 고정 | `"3"` / `"game"` |
| `cid` | 세션마다 | 채팅 채널 짧은 ID (예: `N2gaBX`) |
| `sid` | 세션마다 | 세션 ID. **재사용 필요** |
| `tid` | 매번 증가 | 트랜잭션 ID |
| `bdy.msg` | 우리가 조립 | `{:emojiId:}` |
| `bdy.msgTypeCode` | 고정 | `1` |
| `bdy.msgTime` | 매번 | `Date.now()` |
| `extras.extraToken` | 세션마다 | **재사용 필요** |
| `extras.streamingChannelId` | 채널 | 시청 중인 채널 UUID |
| `extras.emojis` | 우리가 조립 | `{ emojiId: imageUrl }` |

### 왜 URL을 같이 보내는가 (추론)

서버가 `redredLight` 를 이미 알 텐데 URL을 중복해서 싣는 이유. 아래는 관측된
구조에서 끌어낸 **추론이며 치지직이 밝힌 내용이 아니다.**

- **메시지가 자립적이 된다.** 받는 클라이언트가 "이 ID가 무슨 이미지인지"를
  조회할 필요 없이 즉시 렌더링한다. 수만 명에게 실시간 fan-out 하는
  구조에서 조회를 없애는 건 큰 이득이다.
- **시점이 고정된다.** 이미지 파일명에 타임스탬프가 박혀 있다
  (`redredLight_1728386596692.gif`). 스트리머가 이모티콘을 교체·삭제해도
  과거 채팅 로그와 다시보기는 그때 그 이미지로 남는다.
- **채팅 서버가 단순해진다.** 이모티콘 테이블 조인이나 구독 상태 확인 없이
  메시지를 그대로 중계하면 된다.

`emojis` 맵은 **표시용이지 권한용이 아니다.** 권한 검증은 `extraToken` 과
계정의 구독 상태로 따로 이뤄지는 것으로 보인다 (미확인).

`svcid: "game"` 과 이미지 경로 `/static/nng/glive/` 로 미루어, 이 채팅 인프라는
네이버 게임 라이브에서 내려온 것으로 추정된다.

### 어느 필드가 필수인가

**모른다.** 필드를 하나씩 빼며 최소 조합을 찾은 게 아니라 관측한 프레임을
통째로 복제했다. `osType` 같은 건 빼도 동작할 가능성이 높다.

이건 의도한 선택이다. 최소 조합을 찾으려면 실패 메시지를 여러 번 실제 채팅에
쏴야 하고, 무엇보다 **치지직이 나중에 필드를 추가하면 최소 조합은 깨지지만
통째 복제(학습 방식)는 깨지지 않는다.**

---

## 5-1. 채팅 입력창의 이모티콘 형식 (실측)

WebSocket 에 직접 쏘는 대신 **입력창에 넣고 엔터를 치는** 방식을 쓸 때 필요한 정보.

입력창은 `<pre contenteditable="true" class="_input_…">` 이고, 내용을 HTML 로
다룬다. 이모티콘은 `{:id:}` 텍스트가 아니라 **`<img>` 태그**로 들어간다.
그래서 `{:d_1:}` 을 손으로 타이핑하면 글자 그대로 나간다.

치지직이 피커로 넣는 형식:

```html
<img src="https://nng-phinf.pstatic.net/glive/subscription/emoji/<채널ID>/<티어>/<파일명>?type=f60_60">
```

**속성은 `src` 하나뿐이다. 이게 중요하다.**

`title` 이나 `alt` 를 덧붙이면 화면에는 이미지가 정상으로 보이지만 **전송이
되지 않는다.** 치지직이 전송 시 입력창 HTML 을 파싱하면서 `<img src="...">`
형태를 엄격하게 매칭하는 것으로 보이며, 이모티콘으로 인식되지 않으면 유효한
메시지가 만들어지지 않아 엔터를 눌러도 아무 반응이 없다.

emojiId 는 URL 파일명(`<id>_<타임스탬프>.<확장자>`)에서 역으로 뽑아내므로
따로 실을 필요가 없다. 앞서 이미지 이름에서 관찰한 명명 규칙이 이 용도였다.

### 전송

별도 전송 버튼이 없다. 입력 여부에 따라 활성화되는 버튼을 찾아봤지만 없었다.
**엔터 키 이벤트**로만 보낸다.

---

### 핵심 두 가지

**1. `extras` 는 객체가 아니라 JSON 문자열이다.** 이중 인코딩이므로
`JSON.stringify` 를 두 번 거쳐야 한다. 이걸 놓치면 서버가 프레임을 거부한다.

**2. `emojis` 맵이 반드시 같이 나간다.** 공식 오픈 API 가 이모티콘을 못 보내는
이유가 여기서 확정된다. 공식 API 의 요청 필드는 `message` 문자열 하나뿐이라
이 맵을 실을 자리가 없다. 그래서 `{:d_1:}` 이 글자 그대로 표시됐던 것이다.

이미지 URL 은 `emoji-packs` 응답의 `imageUrl` 에 `?type=f60_60` 을 붙인 값이다.

---

## 6. 확장 프로그램 설계 (확정)

세션값(`cid`, `sid`, `extraToken`)을 하드코딩할 수 없으므로 **관찰해서 학습**한다.

```
콘텐츠 스크립트 (chzzk.naver.com/iframe/*, all_frames: true)
  └─ 페이지 컨텍스트에 스크립트 주입   ← WebSocket 접근에 필요
       ├─ WebSocket.prototype.send 후킹
       ├─ cmd 3101 프레임이 지나가면 템플릿으로 저장
       │    (cid, sid, extraToken, 소켓 참조)
       └─ 봉 이벤트 수신 → 템플릿에 msg/emojis/msgTime/tid 만 갈아끼워 전송
```

**학습 조건:** `extraToken` 은 채팅 전송 프레임에만 들어 있으므로, 팬이 최초 1회
**아무 채팅이나 한 번** 쳐야 템플릿이 완성된다. 이모티콘일 필요는 없다.

> 확인해볼 것: 비공식 API 에 채팅 access-token 엔드포인트가 있다는 이야기가 있다.
> 그게 `extraToken` 을 직접 준다면 "채팅 한 번 치기" 단계를 없앨 수 있다.
> 아직 검증 안 됨.

**세션값을 하드코딩하지 않는 것이 중요하다.** 재접속마다 `sid` 와 `extraToken` 이
바뀌므로, 관찰 기반으로 가야 치지직이 프로토콜을 손봐도 재학습만으로 복구된다.
