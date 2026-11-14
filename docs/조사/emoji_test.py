# -*- coding: utf-8 -*-
"""
[보관용 — 더 이상 쓰지 않음]

공식 오픈 API 로는 치지직 이모티콘을 보낼 수 없다는 것을 이 스크립트로
확인했다(2026-08-18). 유니코드 이모지만 전송된다.
그래서 제품은 크롬 확장이 이모티콘 피커를 클릭하는 방식으로 갔고,
이 파일은 그 결론에 도달한 근거로만 남겨 둔다.

여기 있던 CLIENT_ID / CLIENT_SECRET 는 비워 두었다. 발급받은 값을 다시
넣지 말 것 — 이 폴더는 나중에 공개 저장소에 올라갈 수 있다.
자세한 내용은 docs/emoji-reference.md 참고.

--------------------------------------------------------------------------
아래는 당시 검증 절차 기록
--------------------------------------------------------------------------
치지직 오픈 API로 이모티콘 전송이 되는지 확인하는 테스트 스크립트.

공식 문서에는 /open/v1/chats/send 의 요청 필드가 message(문자열, 최대 100자)
하나뿐이고 이모티콘에 대한 언급이 전혀 없다. 문서만 봐서는 "지원 안 함"인지
"그냥 안 적혀 있는 것"인지 구분이 안 되므로, 실제로 쏴 보고 채팅창을 눈으로
확인하는 것이 유일한 확인 방법이다.

표준 라이브러리만 사용한다 (pip install 불필요).

--------------------------------------------------------------------------
사전 준비
--------------------------------------------------------------------------
1) https://developers.chzzk.naver.com 에서 애플리케이션 등록
   - 앱 이름에 'chzzk', '치지직', 'naver', '네이버' 를 넣으면 거부된다
   - 채팅 전송 관련 스코프를 반드시 체크할 것
   - Redirect URI 를 하나 등록 (예: http://localhost:8080/callback)
2) CLIENT_ID / CLIENT_SECRET 를 아래에 입력
3) py emoji_test.py auth   -> 출력된 URL 을 브라우저로 열고 로그인/동의
4) 리다이렉트된 주소창을 통째로 복사
   (페이지 자체는 '연결할 수 없음'이 뜨는 게 정상이다. 주소창만 보면 된다)
5) py emoji_test.py token "<주소창 전체>"   -> accessToken 획득

   반드시 큰따옴표로 감쌀 것. PowerShell 은 & 를 명령 연산자로 해석해서
   따옴표 없이 넣으면 "앰퍼샌드 문자를 사용할 수 없습니다" 오류가 난다.
   code 는 일회용이고 금방 만료되니 바로 실행할 것.

6) py emoji_test.py send <accessToken> [구독이모티콘키]

윈도우에서 'python' 은 스토어 스텁이라 동작하지 않는다. 'py' 를 쓸 것.

--------------------------------------------------------------------------
구독 전용 이모티콘 키 찾는 법
--------------------------------------------------------------------------
기본 이모티콘은 d_1, d_47 처럼 'd_' 로 시작하지만, 스트리머 구독 전용
이모티콘은 채널별 키를 쓴다. 찾는 방법:

  1. 크롬으로 해당 방송 접속 후 F12
  2. Network 탭 -> WS 필터 -> 채팅 연결 클릭 -> Messages
  3. 채팅창에서 구독 이모티콘을 하나 보낸다
  4. 방금 나간 프레임의 msg 값에서 {: :} 안의 문자열이 그 키다
     동시에 extras.emojis 에 '키 -> 이미지 URL' 맵이 붙는지도 확인할 것.
     이 맵이 붙는다면, 그 필드가 없는 공식 API 로는 렌더링이 안 될 가능성이 크다.

구독 전용 이모티콘은 보내는 계정이 그 채널 구독자여야 한다. 비구독 계정으로
테스트하면 실패하는 게 정상이며, API 문제와 구분해야 한다.

--------------------------------------------------------------------------
주의
--------------------------------------------------------------------------
6번은 실제 방송 채팅에 메시지를 6~8개 남긴다. 본인 채널에서, 시청자가 없을 때
돌리는 것을 권한다.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- 설정
CLIENT_ID     = ""   # <- 발급받은 값 입력
CLIENT_SECRET = ""   # <- 발급받은 값 입력
REDIRECT_URI  = "http://localhost:8080/callback"

# 공식 문서에 베이스 호스트가 명시돼 있지 않아 추정한 값이다.
# 404 가 나면 개발자센터 앱 상세 화면에 적힌 호스트로 바꿀 것.
API_BASE  = "https://openapi.chzzk.naver.com"
AUTH_PAGE = "https://chzzk.naver.com/account-interlock"

# ---------------------------------------------------------------- 공통
def request(method, url, body=None, headers=None):
    """요청/응답을 그대로 찍어준다. 404나 스코프 오류를 바로 알아보기 위함."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)

    print(f"  -> {method} {url}")
    if body is not None:
        print(f"     body: {json.dumps(body, ensure_ascii=False)}")

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read().decode("utf-8")
            print(f"  <- {res.status} {raw}")
            return res.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        print(f"  <- {e.code} {raw}")
        return e.code, None
    except Exception as e:
        print(f"  <- 실패: {e}")
        return None, None


# ---------------------------------------------------------------- 1단계
def cmd_auth():
    if not CLIENT_ID:
        print("CLIENT_ID 를 먼저 입력하세요.")
        return
    state = "chzzktest123"
    q = urllib.parse.urlencode({
        "clientId": CLIENT_ID,
        "redirectUri": REDIRECT_URI,
        "state": state,
    })
    print("아래 URL 을 브라우저에서 열고 로그인/동의하세요:\n")
    print(f"  {AUTH_PAGE}?{q}\n")
    print("동의 후 리다이렉트된 주소창을 통째로 복사해서 다음을 실행하세요.")
    print("반드시 큰따옴표로 감쌀 것 (PowerShell 이 & 를 연산자로 해석함):\n")
    print('  py emoji_test.py token "<주소창 전체 붙여넣기>"')


# ---------------------------------------------------------------- 2단계
def parse_code(raw):
    """
    주소창 전체를 붙여넣어도, code 값만 붙여넣어도 동작하도록 한다.
    PowerShell 에서 & 때문에 잘려 들어오는 사고를 막기 위함이다.
    반환: (code, state)
    """
    raw = raw.strip().strip('"').strip("'")

    if "code=" in raw:
        # URL 전체 또는 쿼리스트링 조각
        query = raw.split("?", 1)[1] if "?" in raw else raw
        parsed = urllib.parse.parse_qs(query)
        code = (parsed.get("code") or [""])[0]
        state = (parsed.get("state") or [""])[0]
        return code, state

    return raw, ""


def cmd_token(raw_code, state_arg=None):
    code, state_from_url = parse_code(raw_code)
    state = state_arg or state_from_url or "chzzktest123"

    if not code:
        print("code 를 찾지 못했습니다. 주소창 전체를 큰따옴표로 감싸서 넘겨주세요.")
        return
    if "&" in code or " " in code:
        print(f"code 값이 이상합니다: {code!r}")
        print("큰따옴표로 감싸지 않아 잘렸을 수 있습니다.")
        return

    print(f"code  = {code}")
    print(f"state = {state}\n")
    print("[액세스 토큰 요청]")
    status, res = request("POST", f"{API_BASE}/auth/v1/token", {
        "grantType": "authorization_code",
        "clientId": CLIENT_ID,
        "clientSecret": CLIENT_SECRET,
        "code": code,
        "state": state,
    })
    if res and "content" in res:
        res = res["content"]
    if res and res.get("accessToken"):
        print(f"\naccessToken = {res['accessToken']}")
        print(f"\n다음을 실행하세요:\n  py emoji_test.py send {res['accessToken']}")
    else:
        print("\n토큰을 받지 못했습니다. 위 응답 내용을 확인하세요.")


# ---------------------------------------------------------------- 3단계
# 확인하려는 것: message 필드에 이모티콘 코드를 넣으면 채팅창에 이미지로
# 렌더링되는가, 아니면 '{:d_1:}' 이라는 글자 그대로 나오는가.
#
# 기본 이모티콘(d_*)과 스트리머 구독 전용 이모티콘은 키 형식이 다르고,
# 구독 전용은 보내는 계정이 구독자여야 한다. 둘 다 확인해야 한다.
def build_tests(sub_key=None):
    tests = [
        ("1. 기준선 (일반 텍스트)",       "테스트1 일반텍스트"),
        ("2. 기본 이모티콘 코드",          "테스트2 {:d_1:}"),
        ("3. 다른 기본 이모티콘",          "테스트3 {:d_47:}"),
        ("4. 코드 단독 전송",              "{:d_1:}"),
        ("5. 유니코드 이모지 (대조군)",     "테스트5 \U0001F600"),
        ("6. 기본 이모티콘 2개",           "테스트6 {:d_1:}{:d_2:}"),
    ]
    if sub_key:
        tests += [
            ("7. 구독 전용 이모티콘",       f"테스트7 {{:{sub_key}:}}"),
            ("8. 구독 전용 단독",           f"{{:{sub_key}:}}"),
        ]
    return tests


def cmd_send(token, sub_key=None):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{API_BASE}/open/v1/chats/send"
    tests = build_tests(sub_key)

    if not sub_key:
        print("* 구독 전용 이모티콘 키가 없어 기본 이모티콘만 확인합니다.")
        print("  구독 전용도 확인하려면:")
        print("    py emoji_test.py send <accessToken> <구독이모티콘키>")
        print("  키 찾는 법은 파일 상단 주석 참고.\n")

    print(f"실제 채팅에 메시지 {len(tests)}개를 보냅니다. 계속하려면 Enter, 취소는 Ctrl+C")
    input()

    results = []
    for label, message in tests:
        print(f"\n[{label}]")
        status, res = request("POST", url, {"message": message}, headers)
        results.append((label, message, status))
        time.sleep(1.5)   # 도배 방지 간격

    print("\n" + "=" * 70)
    print("전송 결과 (API 응답 기준)")
    print("=" * 70)
    for label, message, status in results:
        mark = "성공" if status == 200 else f"실패({status})"
        print(f"  {mark:10} {label:26} {message}")

    print("\n" + "=" * 70)
    print("이제 방송 채팅창을 눈으로 확인하세요. 판정 기준:")
    print("=" * 70)
    print("  2,3,4,6번이 이모티콘 '이미지'로 보인다  -> 기본 이모티콘 지원됨")
    print("  '{:d_1:}' 글자 그대로 보인다            -> 미지원. 공식 API로는 불가")
    print("  전송은 성공했는데 채팅에 아예 안 보임    -> 서버가 필터링 중")
    print("  1,5번만 정상                            -> 텍스트/유니코드만 가능")
    if sub_key:
        print("  7,8번도 이미지로 보인다                 -> 구독 전용까지 가능")
        print("  7,8번만 글자로 나온다                   -> 계정 구독 상태 확인 필요")


# ---------------------------------------------------------------- 진입점
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "auth":
        cmd_auth()
    elif cmd == "token" and len(sys.argv) >= 3:
        cmd_token(sys.argv[2], sys.argv[3] if len(sys.argv) >= 4 else None)
    elif cmd == "send" and len(sys.argv) >= 3:
        cmd_send(sys.argv[2], sys.argv[3] if len(sys.argv) >= 4 else None)
    else:
        print(__doc__)
