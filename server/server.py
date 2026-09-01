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
로컬 테스트용이라 평문 HTTP 다. 인터넷에 올릴 때는 반드시 HTTPS/WSS 뒤에
두어야 한다. 확장은 https 페이지에서 동작하므로 ws:// 로는 붙지 못한다.
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
    # 봉과 확장이 같은 방에 있어야 서로 연결된다.
    "room": "crown-test",
    # 스트리머 본인용 만능 키. test.html / monitor 같은 도구가 쓴다.
    # 팬의 봉과 확장은 이걸 몰라도 된다 — 설정 페이지가 방마다 따로 만들고
    # 서버가 rooms.json 에 등록한다.
    "admin_token": "change-me",
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


def short(room):
    """
    콘솔에 방 코드를 통째로 찍지 않는다.

    이 서버 창은 스트리머 화면에 떠 있을 수 있고, 여기 흐르는 건 팬들의
    방 코드다. 어느 방인지 구분할 만큼만 남기면 충분하다.
    """
    room = str(room or "")
    return room[:10] + "…" if len(room) > 10 else room


# ---------------------------------------------------------------- 방 관리
class Rooms:
    """방 하나당 확장 WebSocket 여러 개가 붙을 수 있다 (탭 여러 개 등)."""

    def __init__(self):
        self._clients = defaultdict(set)
        self._cid = {}                # ws -> 확장 설치본 id
        self.log = deque(maxlen=50)   # 최근 이벤트 (테스트 페이지에서 확인용)

    async def add(self, room, ws, cid=""):
        """
        같은 확장이 이미 붙어 있으면 옛 소켓을 끊는다.

        확장의 서비스워커는 수시로 죽었다 살아나는데, 그때 새 소켓을 열면서
        옛 소켓이 여기 남아 있을 수 있다. 그대로 두면 한 방에 소켓이 둘이 되고
        이벤트가 두 번씩 배달된다 — 이모티콘이 두 개씩 들어간다.
        """
        if cid:
            for old in [w for w in self._clients[room] if self._cid.get(w) == cid]:
                LOG.info("같은 확장의 옛 연결을 끊습니다: room=%s", short(room))
                self._clients[room].discard(old)
                self._cid.pop(old, None)
                try:
                    await old.close(code=4000, message=b"replaced")
                except Exception:
                    pass

        self._clients[room].add(ws)
        if cid:
            self._cid[ws] = cid
        LOG.info("확장 연결: room=%s (총 %d)", short(room), len(self._clients[room]))

    def remove(self, room, ws):
        self._clients[room].discard(ws)
        self._cid.pop(ws, None)
        if not self._clients[room]:
            self._clients.pop(room, None)
        LOG.info("확장 해제: room=%s", short(room))

    def count(self, room):
        return len(self._clients.get(room, ()))

    async def broadcast(self, room, payload):
        targets = list(self._clients.get(room, ()))
        if not targets:
            LOG.warning("room=%s 에 연결된 확장이 없습니다 — 이벤트를 버립니다", short(room))
            return 0

        data = json.dumps(payload, ensure_ascii=False)
        sent = 0
        for ws in targets:
            if ws.closed:
                self.remove(room, ws)
                continue
            try:
                await ws.send_str(data)
                sent += 1
            except Exception as e:
                LOG.warning("전송 실패, 연결을 정리합니다: %s", e)
                self.remove(room, ws)
        return sent


ROOMS = Rooms()

# 방마다 마지막으로 받은 봉 상태. 확장이 나중에 붙어도 바로 보여줄 수 있다.
STICKS = {}


# ---------------------------------------------------------------- 핸들러
# ------------------------------------------------------------------ 방 등록부

ROOMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rooms.json")
_registry = None


def _load_registry():
    """방 코드 -> 토큰. 팬마다 하나씩 생긴다."""
    global _registry
    if _registry is None:
        try:
            with io.open(ROOMS_FILE, encoding="utf-8") as f:
                _registry = json.load(f)
        except Exception:
            _registry = {}
    return _registry


def _save_registry():
    tmp = ROOMS_FILE + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(_registry, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ROOMS_FILE)


def check_room_token(room, token, cfg):
    """
    방의 토큰을 확인한다. 처음 보는 방이면 그 토큰으로 등록한다.

    팬이 코드를 옮겨 적지 않게 하려면, 설정 페이지가 만든 값을 서버가
    그대로 받아들이는 수밖에 없다. 방 코드가 충분히 길고 무작위라
    남이 먼저 채가려면 그 코드를 맞혀야 하는데, 그건 현실적으로 어렵다.

    스트리머 본인은 config.json 의 admin_token 으로 아무 방에나 들어간다
    (test.html, monitor 같은 도구용).
    """
    if not token:
        return False

    admin = str(cfg.get("admin_token") or "")
    if admin and secrets.compare_digest(token, admin):
        return True

    reg = _load_registry()
    known = reg.get(room)

    if known is None:
        if len(room) < 8:
            LOG.warning("방 코드가 너무 짧아 등록을 거절: %s", short(room))
            return False
        reg[room] = token
        _save_registry()
        LOG.info("새 방 등록: %s", short(room))
        return True

    return secrets.compare_digest(token, str(known))


async def handle_stick(request):
    """
    봉이 보내는 이벤트.

        POST /api/stick
        { "room": "...", "token": "...", "action": "add", "motion": "SWAY_LR" }
        { "room": "...", "token": "...", "action": "send" }

    action=add  는 motion 을 이모티콘으로 바꿔 확장에 넘긴다.
    action=send 는 그대로 넘긴다 (봉의 버튼).
    """
    cfg = request.app["cfg"]

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="JSON 이 아닙니다")

    room = str(body.get("room") or cfg["room"])
    token = str(body.get("token") or "")
    action = str(body.get("action") or "")

    if not check_room_token(room, token, cfg):
        LOG.warning("토큰 불일치: room=%s", short(room))
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
        STICKS[room] = (time.monotonic(), payload)

        n = await ROOMS.broadcast(room, dict(payload, age=0))
        return web.json_response({"ok": True, "delivered": n})

    else:
        raise web.HTTPBadRequest(text="action 은 add / send / clear 중 하나여야 합니다")

    n = await ROOMS.broadcast(room, payload)
    # 시각이 없으면 방금 온 이벤트인지 아까 것인지 구분할 수 없다.
    ROOMS.log.append({
        "at": time.strftime("%H:%M:%S"), "room": short(room), **payload, "delivered": n,
    })
    LOG.info("봉 → %s: %s (확장 %d개)", short(room), payload, n)

    return web.json_response({"ok": True, "delivered": n, "payload": payload})


async def handle_ws(request):
    """확장이 붙는 곳. GET /ws?room=...&token=..."""
    cfg = request.app["cfg"]
    room = request.query.get("room") or cfg["room"]
    token = request.query.get("token") or ""

    if not check_room_token(room, token, cfg):
        raise web.HTTPUnauthorized(text="token 이 맞지 않습니다")

    ws = web.WebSocketResponse(heartbeat=25)   # 유휴 종료 방지용 핑
    await ws.prepare(request)
    await ROOMS.add(room, ws, request.query.get("cid") or "")

    try:
        await ws.send_str(json.dumps({
            "action": "hello", "room": room,
            # 봉의 설정 페이지가 이걸로 서버 주소 칸을 자동으로 채운다
            "stickUrl": f"http://{lan_ip()}:{request.app['port']}",
        }))
        # 봉이 방금 보고했을 수도 20분 전일 수도 있다. 있으면 보여주되,
        # 몇 초 전 것인지 반드시 같이 준다.
        #
        # 이걸 안 주면 확장이 "지금 막 받았다" 로 도장을 찍는다. 봉이 꺼진 지
        # 한참인데도 확장을 새로 열 때마다 "켜져 있음" 으로 보이게 된다.
        if room in STICKS:
            got_at, payload = STICKS[room]
            age = int(time.monotonic() - got_at)
            await ws.send_str(json.dumps(dict(payload, age=age)))
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                # 확장이 결과를 돌려보내면 로그에 남긴다
                LOG.info("확장 → 서버 [%s]: %s", short(room), msg.data[:200])
            elif msg.type == WSMsgType.ERROR:
                LOG.warning("WebSocket 오류: %s", ws.exception())
    finally:
        ROOMS.remove(room, ws)
    return ws


async def handle_status(request):
    """
    서버 상태. room 을 주면 그 방만, 안 주면 전체를 본다.

    설정 페이지가 "확장이 서버에 붙었나" 를 여기서 확인한다.
    토큰은 필요 없다 — 방 코드를 아는 쪽만 자기 방을 물어볼 수 있고,
    돌려주는 것도 붙어 있는 개수뿐이다.
    """
    cfg = request.app["cfg"]
    room = request.query.get("room")

    if room:
        return web.json_response({
            "room": room,
            "registered": room in _load_registry(),
            "connected": ROOMS.count(room),
            "motions": cfg["motions"],
            "recent": [r for r in ROOMS.log if r.get("room") == short(room)][-10:],
        })

    # 방 목록은 스트리머 본인만 본다. 그냥 나열하면 방 코드가 공개되고,
    # 그러면 방 코드는 더 이상 아무것도 가려주지 못한다.
    if not check_room_token("", request.query.get("token") or "", cfg):
        return web.json_response({
            "rooms": None,
            "connected_total": sum(ROOMS.count(r) for r in _load_registry()),
            "motions": cfg["motions"],
        })

    return web.json_response({
        "rooms": sorted(_load_registry().keys()),
        "connected_total": sum(ROOMS.count(r) for r in _load_registry()),
        "motions": cfg["motions"],
        "recent": list(ROOMS.log)[-10:],
    })


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
    room = request.headers.get("X-Room") or cfg["room"]
    if not check_room_token(room, request.headers.get("X-Token") or "", cfg):
        LOG.warning("로그 토큰 불일치: room=%s", short(room))
        raise web.HTTPUnauthorized(text="bad token")
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
