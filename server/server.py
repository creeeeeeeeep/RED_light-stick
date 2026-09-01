# -*- coding: utf-8 -*-
"""
크라운 응원봉 중계 서버.

    응원봉(ESP32) --HTTP POST--> [서버] --WebSocket--> 크롬 확장 --> 치지직 채팅

--------------------------------------------------------------------------
왜 이 구조인가
--------------------------------------------------------------------------
* 봉 → 서버는 HTTP POST 다. ESP-IDF 기본 esp_http_client 로 충분해서 별도
  컴포넌트가 필요 없다.
* 서버 → 확장은 WebSocket 이어야 한다. MV3 확장의 서비스워커는 30초 유휴 시
  종료되는데, WebSocket 통신이 그 타이머를 리셋해 준다. 폴링이나 SSE 로는
  봉을 흔들어도 확장이 자고 있어 반응하지 않을 수 있다.
* 확장 쪽 네트워크 연결은 반드시 백그라운드(서비스워커)에서 한다.
  콘텐츠 스크립트는 치지직 페이지의 CSP 를 따르므로 외부 서버 연결이 막힌다.
* 이 서버는 팬 각자의 컴퓨터에서 돈다. 봉도 브라우저도 같은 집 안에 있으니
  바깥에 둘 이유가 없다. 그래서 방(room) 개념이 없다 — 나눌 상대가 없다.

--------------------------------------------------------------------------
실행
--------------------------------------------------------------------------
    py -m pip install aiohttp
    py server.py

    http://localhost:8787/test  브라우저로 열면 봉을 흉내낼 수 있다.
                                봉을 만들기 전에 서버→확장→채팅 흐름을
                                통째로 검증하는 용도.

--------------------------------------------------------------------------
주의
--------------------------------------------------------------------------
집 안에서만 도는 것을 전제로 평문 HTTP 를 쓴다. 확장은 같은 컴퓨터에서
ws://localhost 로 붙으므로 이것으로 충분하다.

인터넷에 내놓을 생각이라면 그때는 HTTPS/WSS 와 방 개념이 다시 필요하다.
"""

import argparse
import asyncio
import io
import json
import logging
import os
import secrets
import time
from collections import defaultdict, deque

from aiohttp import web, WSMsgType

LOG = logging.getLogger("crown")

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

DEFAULT_CONFIG = {
    # 봉이 쓰는 열쇠. 비워 두면 처음 켤 때 서버가 만들어 여기에 적는다.
    # 설정 페이지가 이 값을 받아 봉에 써넣으므로 사람이 볼 일은 없다.
    "token": "",
    # 모션 → 이모티콘. 여기만 고치면 봉을 다시 플래시하지 않아도 된다.
    "motions": {
        "SWAY_LR":  "redredMinidance1",   # 좌우로 흔들기
        "PUMP_UD":  "redredLight",        # 위아래로 찍기
        "VIGOROUS": "redredLight5",       # 격하게 흔들기
    },
    # 한 메시지에 넣을 이모티콘 상한
    "max_per_message": 10,
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        LOG.info("기본 설정을 만들었습니다: %s", CONFIG_PATH)
        return dict(DEFAULT_CONFIG)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def lan_ip():
    """
    이 PC 가 공유기에서 받은 주소.

    봉은 다른 기기라서 localhost 로는 못 온다. 이 주소로 와야 한다.
    팬이 직접 찾아 넣게 하면 거기서 대부분 막히므로, 서버가 알아내서
    확장에 알려주고 설정 페이지가 자동으로 채운다.

    바깥으로 실제 패킷을 보내지는 않는다. UDP 소켓에 목적지를 지정하면
    OS 가 어느 랜카드를 쓸지 정하는데, 그때 정해진 주소를 읽는 것뿐이다.
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# ------------------------------------------------------------- 붙어 있는 확장
class Clients:
    """
    붙어 있는 확장들. 방으로 나누지 않는다 — 서버가 팬마다 자기 컴퓨터에서
    도므로 나눌 상대가 없다. 봉 이벤트는 붙어 있는 전부에게 간다.

    탭을 여러 개 열면 확장 하나가 여러 번 붙을 수 있어서 집합으로 든다.
    """

    def __init__(self):
        self._clients = set()
        self._cid = {}                # ws -> 확장 설치본 id
        self.log = deque(maxlen=50)   # 최근 이벤트 (테스트 페이지에서 확인용)

    async def add(self, ws, cid=""):
        """
        같은 확장이 이미 붙어 있으면 옛 소켓을 끊는다.

        확장의 서비스워커는 수시로 죽었다 살아나는데, 그때 새 소켓을 열면서
        옛 소켓이 여기 남아 있을 수 있다. 그대로 두면 이벤트가 두 번씩
        배달된다 — 이모티콘이 두 개씩 들어간다.
        """
        if cid:
            for old in [w for w in self._clients if self._cid.get(w) == cid]:
                LOG.info("같은 확장의 옛 연결을 끊습니다")
                self._clients.discard(old)
                self._cid.pop(old, None)
                try:
                    await old.close(code=4000, message=b"replaced")
                except Exception:
                    pass

        self._clients.add(ws)
        if cid:
            self._cid[ws] = cid
        LOG.info("확장 연결 (총 %d)", len(self._clients))

    def remove(self, ws):
        self._clients.discard(ws)
        self._cid.pop(ws, None)
        LOG.info("확장 해제 (남은 %d)", len(self._clients))

    def total(self):
        return len(self._clients)

    async def broadcast(self, payload):
        targets = list(self._clients)
        if not targets:
            LOG.warning("붙어 있는 확장이 없습니다 — 이벤트를 버립니다")
            return 0

        data = json.dumps(payload, ensure_ascii=False)
        sent = 0
        for ws in targets:
            if ws.closed:
                self.remove(ws)
                continue
            try:
                await ws.send_str(data)
                sent += 1
            except Exception as e:
                LOG.warning("전송 실패, 연결을 정리합니다: %s", e)
                self.remove(ws)
        return sent


ROOMS = Clients()

# 마지막으로 받은 봉 상태. 확장이 나중에 붙어도 바로 보여줄 수 있다.
# [(받은 시각, 내용)] 한 칸짜리 상자.
STICK = [None]


# ---------------------------------------------------------------- 핸들러
# --------------------------------------------------------------------- 열쇠

"""
방(room) 개념은 없앴다.

방은 여러 팬이 하나의 서버를 나눠 쓸 때 서로를 가르려고 있던 것이다. 서버가
팬마다 자기 컴퓨터에서 도는 지금 구조에서는 나눌 상대가 없다. 그런데도 봉과
확장이 같은 방 이름을 들고 있어야 해서, 한쪽 설정만 지워지면 둘 다 멀쩡히
서버에 붙은 채로 아무 일도 안 일어났다. 실제로 그 상태를 두 번 겪었다.

지금은 서버에 오는 봉 이벤트를 붙어 있는 확장 전부에게 보낸다.

남은 것은 열쇠(token) 하나다. 같은 WiFi 에 있는 다른 사람이 내 채팅에
이모티콘을 쏘는 것만 막으면 되고, 그건 값 하나로 충분하다.

  확장  ws://localhost 로만 붙는다 -> 같은 컴퓨터인 게 증명되므로 열쇠가 필요 없다.
                                     접속하면 서버가 열쇠를 알려준다.
  봉    LAN 을 건너오므로 열쇠를 실어야 한다. 설정 페이지가 위에서 받은 열쇠를
        봉에 써넣는다. 팬은 여전히 아무것도 입력하지 않는다.
"""


def same_token(a, b):
    """
    열쇠 비교. 타이밍 공격을 피하려고 compare_digest 를 쓴다.

    문자열을 그대로 넘기면 안 된다 — ASCII 가 아닌 값이 오면 TypeError 를
    던져서 서버가 500 으로 죽는다. 열쇠는 바깥에서 오는 값이므로 무엇이든
    올 수 있다. 바이트로 바꿔 비교한다.
    """
    return secrets.compare_digest(str(a or "").encode("utf-8"),
                                  str(b or "").encode("utf-8"))


def get_token(cfg):
    """서버의 열쇠. 없으면 만들어 config.json 에 적어둔다."""
    tok = str(cfg.get("token") or "")
    if len(tok) >= 16 and tok != "change-me":
        return tok

    tok = secrets.token_urlsafe(24)
    cfg["token"] = tok
    try:
        with io.open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        LOG.info("열쇠를 새로 만들어 config.json 에 저장했습니다")
    except Exception as e:
        LOG.warning("열쇠를 저장하지 못했습니다 (다음 실행 때 다시 만듭니다): %s", e)
    return tok


def is_local(request):
    """같은 컴퓨터에서 온 연결인가."""
    peer = request.transport.get_extra_info("peername") if request.transport else None
    host = peer[0] if peer else ""
    return host in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


async def handle_stick(request):
    """
    봉이 보내는 이벤트.

        POST /api/stick
        { "token": "...", "action": "add", "motion": "SWAY_LR" }
        { "token": "...", "action": "send" }

    봉이 보내는 room 필드는 무시한다. 옛 펌웨어와의 호환을 위해 받기만 한다.
    """
    cfg = request.app["cfg"]

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="JSON 이 아닙니다")

    token = str(body.get("token") or "")
    action = str(body.get("action") or "")

    if not same_token(token, request.app["token"]):
        LOG.warning("열쇠가 맞지 않는 요청을 거절했습니다 (%s)",
                    request.remote or "출처 불명")
        raise web.HTTPUnauthorized(text="token 이 맞지 않습니다")

    if action == "add":
        motion = str(body.get("motion") or "")
        emoji_id = cfg["motions"].get(motion)
        if not emoji_id:
            raise web.HTTPBadRequest(
                text=f"알 수 없는 모션: {motion} (설정: {list(cfg['motions'])})")
        payload = {"action": "add", "emojiId": emoji_id, "motion": motion}

    elif action == "send":
        payload = {"action": "send"}

    elif action == "clear":
        payload = {"action": "clear"}

    elif action == "status":
        # 봉이 스스로 알리는 상태. 이모티콘과 무관하므로 그대로 흘려보낸다.
        payload = {
            "action": "stick",
            "ip": str(body.get("ip") or ""),
            "fw": str(body.get("fw") or ""),
            "uptime": int(body.get("uptime") or 0),
            "count": int(body.get("count") or 0),
            "led": str(body.get("led") or ""),
            "at": time.strftime("%H:%M:%S"),
        }
        # 언제 받았는지 따로 들고 있는다. 나중에 이 상태를 다시 보낼 때
        # "몇 초 전 것인지" 를 같이 알려주기 위해서다.
        STICK[0] = (time.monotonic(), payload)

        n = await ROOMS.broadcast(dict(payload, age=0))
        return web.json_response({"ok": True, "delivered": n})

    else:
        raise web.HTTPBadRequest(text="action 은 add / send / clear 중 하나여야 합니다")

    n = await ROOMS.broadcast(payload)
    # 시각이 없으면 방금 온 이벤트인지 아까 것인지 구분할 수 없다.
    ROOMS.log.append({"at": time.strftime("%H:%M:%S"), **payload, "delivered": n})
    LOG.info("봉 → %s (확장 %d개)", payload, n)

    return web.json_response({"ok": True, "delivered": n, "payload": payload})


async def handle_ws(request):
    """
    확장이 붙는 곳. GET /ws

    같은 컴퓨터에서 온 연결만 받는다. 서버와 확장은 언제나 같은 PC 에 있으므로
    이것으로 충분하고, 같은 WiFi 의 다른 사람은 들어올 수 없다.
    열쇠를 요구하지 않는 대신, 붙으면 열쇠를 알려준다 — 설정 페이지가 그걸
    봉에 써넣는다.
    """
    if not is_local(request):
        LOG.warning("바깥에서 온 확장 연결을 거절했습니다 (%s)", request.remote)
        raise web.HTTPForbidden(text="같은 컴퓨터에서만 붙을 수 있습니다")

    ws = web.WebSocketResponse(heartbeat=25)   # 유휴 종료 방지용 핑
    await ws.prepare(request)
    await ROOMS.add(ws, request.query.get("cid") or "")

    try:
        await ws.send_str(json.dumps({
            "action": "hello",
            # 설정 페이지가 이 둘로 봉을 설정한다. 팬은 아무것도 입력하지 않는다.
            "stickUrl": f"http://{lan_ip()}:{request.app['port']}",
            "token": request.app["token"],
        }))

        # 봉이 방금 보고했을 수도, 20분 전일 수도 있다. 몇 초 전 것인지 같이 준다.
        if STICK[0]:
            got_at, payload = STICK[0]
            await ws.send_str(json.dumps(
                dict(payload, age=int(time.monotonic() - got_at))))

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                LOG.info("확장 → 서버: %s", msg.data[:200])
    finally:
        ROOMS.remove(ws)
    return ws


async def handle_status(request):
    """서버 상태. 붙어 있는 확장 수와 최근 이벤트."""
    cfg = request.app["cfg"]
    stick = None
    if STICK[0]:
        got_at, payload = STICK[0]
        stick = dict(payload, age=int(time.monotonic() - got_at))

    out = {
        "connected": ROOMS.total(),
        "stick": stick,
        "motions": cfg["motions"],
        "recent": list(ROOMS.log)[-10:],
    }
    # 같은 컴퓨터에서 물어보면 열쇠도 준다. test.html 이 이걸로 자동으로 채운다.
    # 확장이 붙을 때와 같은 기준이다 — localhost 면 같은 컴퓨터가 증명된다.
    if is_local(request):
        out["token"] = request.app["token"]
    return web.json_response(out)


def _page(name):
    """정적 HTML 하나를 돌려주는 핸들러를 만든다."""
    async def handler(request):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    return handler


# --------------------------------------------------------------- 펌웨어 갱신

FIRMWARE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firmware")


def _firmware_on_disk():
    """firmware/ 에서 cheerstick-<버전>.bin 중 가장 최근 것을 고른다."""
    try:
        names = [n for n in os.listdir(FIRMWARE_DIR)
                 if n.startswith("cheerstick-") and n.endswith(".bin")]
    except FileNotFoundError:
        return None, None
    if not names:
        return None, None
    newest = max(names, key=lambda n: os.path.getmtime(os.path.join(FIRMWARE_DIR, n)))
    return newest[len("cheerstick-"):-len(".bin")], newest


async def handle_firmware(request):
    """
    봉이 주기적으로 물어본다. GET /api/firmware?room=..&ver=..

    올려둘 게 없으면 version 을 비워 보낸다. 봉은 그러면 아무것도 하지 않는다.
    """
    version, name = _firmware_on_disk()
    if not version:
        return web.json_response({"version": ""})

    # 봉이 받으러 올 주소는 봉이 우리를 부른 주소와 같은 곳이어야 한다.
    # 설정에 적힌 주소를 그대로 쓰면 터널 뒤에서 어긋난다.
    base = str(request.url.origin())

    # 봉은 기본적으로 '더 새것' 만 받는다. 옛 버전으로 되돌려야 할 때만
    # firmware/FORCE 파일을 두면 봉이 내려가는 것도 받아들인다.
    forced = os.path.exists(os.path.join(FIRMWARE_DIR, "FORCE"))

    return web.json_response({
        "version": version,
        "url": f"{base}/firmware/{name}",
        "force": forced,
    })


# ------------------------------------------------------------------ 모션 로그

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


async def handle_log(request):
    """
    개발자 빌드가 흔든 기록을 흘려보내는 곳. 한 줄에 TUNE,... 하나.

    토큰이 맞아야 받는다 — 아무나 디스크를 채우게 두지 않는다.
    """
    cfg = request.app["cfg"]
    if not same_token(request.headers.get("X-Token"), request.app["token"]):
        LOG.warning("열쇠가 맞지 않는 로그를 거절했습니다")
        raise web.HTTPUnauthorized(text="bad token")
    room = request.headers.get("X-Room") or "crown"
    body = await request.text()
    if not body.strip():
        return web.json_response({"ok": True, "lines": 0})

    os.makedirs(LOG_DIR, exist_ok=True)
    # 방마다 날짜별로 한 파일. 세션을 나누면 나중에 짝맞추기가 번거롭다.
    safe = "".join(c for c in room if c.isalnum() or c in "-_")
    path = os.path.join(LOG_DIR, f"{safe}-{time.strftime('%Y%m%d')}.csv")

    header = "time,gesture,v,h,total,peak,gyro,strokes,tilt,ma\n"
    new = not os.path.exists(path)
    with io.open(path, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write(header)
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("TUNE,"):
                f.write(line[len("TUNE,"):] + "\n")

    n = body.count("TUNE,")
    LOG.info("로그 %d줄 -> %s", n, os.path.basename(path))
    return web.json_response({"ok": True, "lines": n})


# ------------------------------------------------------------ ESP Launchpad

LAUNCHPAD_DIR = os.path.join(HERE, "launchpad")


async def handle_launchpad(request):
    """
    ESP Launchpad 용 파일 (config.toml, 합쳐진 펌웨어).

    Launchpad 는 https://espressif.github.io 에서 돌면서 이 파일들을 브라우저로
    가져간다. 다른 출처라서 CORS 헤더가 없으면 막힌다.

    그리고 Launchpad 가 https 이므로 이 서버도 https 여야 한다. 평문 http 는
    브라우저가 혼합 콘텐츠로 차단한다. 터널을 붙인 뒤에 쓸 수 있다는 뜻이다.
    """
    name = request.match_info.get("name", "")
    if "/" in name or "\\" in name or name.startswith("."):
        raise web.HTTPNotFound()

    path = os.path.join(LAUNCHPAD_DIR, name)
    if not os.path.isfile(path):
        raise web.HTTPNotFound()

    ctype = "text/plain" if name.endswith(".toml") else "application/octet-stream"
    return web.FileResponse(path, headers={
        "Access-Control-Allow-Origin": "*",
        "Content-Type": ctype,
    })


def build_app(cfg, port=8787):
    app = web.Application()
    app["cfg"] = cfg
    app["port"] = port
    app["token"] = get_token(cfg)
    app.router.add_post("/api/stick", handle_stick)
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/firmware", handle_firmware)
    app.router.add_post("/api/log", handle_log)
    os.makedirs(FIRMWARE_DIR, exist_ok=True)
    app.router.add_static("/firmware/", FIRMWARE_DIR)
    os.makedirs(LAUNCHPAD_DIR, exist_ok=True)
    app.router.add_get("/launchpad/{name}", handle_launchpad)
    app.router.add_get("/test", _page("test.html"))
    # Web Serial 은 보안 컨텍스트를 요구한다. localhost 는 허용되므로
    # 이 서버로 열면 file:// 과 달리 정상 동작한다.
    app.router.add_get("/monitor", _page("monitor.html"))
    app.router.add_get("/", lambda r: web.HTTPFound("/test"))
    return app


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    cfg = load_config()

    if cfg.get("admin_token") == "change-me":
        LOG.warning("admin_token 이 기본값입니다. config.json 에서 바꾸세요.")

    LOG.info("모션 매핑: %s", cfg["motions"])
    LOG.info("봉 시뮬레이터:  http://localhost:%d/test", args.port)
    LOG.info("모션 모니터:    http://localhost:%d/monitor", args.port)

    web.run_app(build_app(cfg, args.port), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
