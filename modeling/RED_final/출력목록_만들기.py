# -*- coding: utf-8 -*-
u"""
출력 목록 사진을 만든다.

카페에 올렸을 때 "뭘 몇 개 뽑아야 하는지" 가 한 눈에 보여야 한다.
STL 을 직접 읽어 그리므로, 모델을 고치면 다시 돌리기만 하면 된다.

그리는 방법
-----------
OpenGL 을 쓰지 않는다. 헤드리스에서 자주 깨지고, 깨지면 원인 찾기가 번거롭다.
삼각형을 화면 좌표로 옮기고 깊이순으로 덮어 그린다(화가 알고리즘). 면 하나를
한 가지 색으로 칠하는 평면 음영이라 3D 프린트 출력물처럼 보인다.
"""
import io, os, struct, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PRINT_DIR = os.path.join(HERE, "print")
OUT = os.path.join(HERE, "출력목록.png")

SS = 3                      # 수퍼샘플링 배수. 계단을 없앤다
TILE = 300                  # 부품 한 칸의 그림 크기 (최종 픽셀)
COLS = 5

# 색은 추천 소재 색을 따른다 — 보는 사람이 바로 짝지을 수 있게
RED, CLEAR, YELLOW, BLACK, TEST = (
    (196, 43, 54), (176, 206, 214), (235, 189, 46), (60, 60, 64), (150, 150, 155))

PARTS = [
    (u"05_handle_RED.stl",     u"손잡이",      1, u"ABS 레드",   RED,    u"버튼이 같이 출력됨 · 브림", False, 24.0),
    (u"07a_tray_RED.stl",      u"트레이",      1, u"ABS 레드",   RED,    u"평평한 면이 바닥 · 브림", False, 24.0),
    (u"07b_lid_RED.stl",       u"뚜껑",        1, u"ABS 레드",   RED,    u"평평한 면이 바닥 · 브림", False, 24.0),
    (u"07c_ring_RED.stl",      u"링",          1, u"ABS 레드",   RED,    u"", False, 24.0),
    (u"03_boardseat_RED.stl",  u"보드 받침",   1, u"ABS 레드",   RED,    u"", False, 24.0),
    (u"02_crown_RED.stl",      u"왕관",        1, u"ABS 레드",   RED,    u'이름 "RED" 음각', False, 24.0),
    (u"01_dome_CLEAR.stl",     u"돔",          1, u"PETG 투명",  CLEAR,  u"첨탑까지 한 몸", False, 24.0),
    (u"09_cross_YELLOW.stl",   u"십자",        1, u"PLA 노랑",   YELLOW, u"눕혀서", False, 72.0),
    (u"16_key_RED.stl",        u"돌리개",      1, u"아무거나",   RED,    u"링 돌리는 공구", False, 24.0),
]


def load_stl(path):
    u"""바이너리 STL → (삼각형 N×3×3) 배열."""
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack("<I", data[80:84])[0]
    body = np.frombuffer(data, dtype=np.uint8, count=n * 50, offset=84)
    body = body.reshape(n, 50)
    # 각 줄: 법선 3 + 꼭짓점 9 = 12 float (48바이트) + 속성 2바이트
    tri = body[:, 12:48].copy().view(np.float32).reshape(n, 3, 3)
    return tri.astype(np.float64)


def best_view(tri, elev=24.0):
    u"""
    베드에 놓인 그대로, 살짝 내려다본 각도.

    STL 은 전부 출력 방향으로 맞춰져 있다(Z 가 위). 슬라이서에서 보는 모습과
    같게 두면 받는 사람이 바로 알아본다. 돌리는 것은 Z 축 회전뿐이고, 그중
    그림자가 제일 넓은 쪽을 쓴다 — 납작한 부품이 옆에서 보여 막대처럼 나오는
    것만 피하면 된다.
    """
    t = math.radians(-(90.0 - elev))          # 음수라야 모델의 +Z 가 화면 위로 온다
    Rtilt = np.array([[1, 0, 0],
                      [0, math.cos(t), -math.sin(t)],
                      [0, math.sin(t), math.cos(t)]])
    v0 = tri.reshape(-1, 3)

    best, bestR = -1.0, Rtilt
    for az in range(0, 360, 10):
        a = math.radians(az)
        Rz = np.array([[math.cos(a), -math.sin(a), 0],
                       [math.sin(a), math.cos(a), 0],
                       [0, 0, 1]])
        R = Rtilt @ Rz
        p = v0 @ R.T
        lo, hi = p[:, :2].min(axis=0), p[:, :2].max(axis=0)
        w, h = hi - lo
        if w <= 0 or h <= 0:
            continue
        if w * h > best:
            best, bestR = w * h, R
    return bestR


def render(path, color, px, flip=False, elev=24.0):
    u"""부품 하나를 그린다. 배경은 투명."""
    tri = load_stl(path)
    S = px * SS

    R = best_view(tri, elev)
    if flip:
        # 글자처럼 앞뒤가 뒤집혀 보이면 반대쪽에서 본다
        R = np.array([[-1, 0, 0], [0, 1, 0], [0, 0, -1]]) @ R
    v = tri.reshape(-1, 3) @ R.T

    # ---- 화면에 꽉 차게 ----
    lo, hi = v.min(axis=0), v.max(axis=0)
    span = max(hi[0] - lo[0], hi[1] - lo[1]) or 1.0
    scale = (S * 0.86) / span
    mid = (hi + lo) / 2.0
    v[:, 0] = (v[:, 0] - mid[0]) * scale + S / 2.0
    v[:, 1] = -(v[:, 1] - mid[1]) * scale + S / 2.0
    v = v.reshape(-1, 3, 3)

    # ---- 면 법선과 음영 ----
    e1, e2 = v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]
    nrm = np.cross(e1, e2)
    ln = np.linalg.norm(nrm, axis=1)
    ok = ln > 1e-12
    v, nrm, ln = v[ok], nrm[ok], ln[ok]
    nrm /= ln[:, None]

    light = np.array([-0.35, -0.62, -0.70])
    light /= np.linalg.norm(light)
    lam = np.clip(nrm @ light, 0, 1)
    shade = 0.34 + 0.66 * lam ** 0.85          # 완전히 검은 면은 만들지 않는다

    order = np.argsort(v[:, :, 2].mean(axis=1))   # 먼 것부터
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r, g, b = color
    for i in order:
        t = v[i]
        k = shade[i]
        d.polygon([(t[0][0], t[0][1]), (t[1][0], t[1][1]), (t[2][0], t[2][1])],
                  fill=(int(r * k), int(g * k), int(b * k), 255))
    return im.resize((px, px), Image.LANCZOS)


def font(sz, bold=False):
    for name in ((u"malgunbd.ttf", u"malgun.ttf") if bold else (u"malgun.ttf",)):
        try:
            return ImageFont.truetype(os.path.join(os.environ["WINDIR"], "Fonts", name), sz)
        except Exception:
            pass
    return ImageFont.load_default()


def main():
    rows = (len(PARTS) + COLS - 1) // COLS
    PAD, HEAD, CAP = 26, 150, 104
    W = PAD * 2 + COLS * TILE + (COLS - 1) * PAD
    H = HEAD + rows * (TILE + CAP) + (rows - 1) * PAD + PAD

    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)

    d.text((PAD, 30), u"RED 응원봉 — 3D 출력 목록", font=font(44, True), fill=(17, 17, 17))
    d.text((PAD, 88), u"전부 서포트 없이 · 파일 방향 그대로 · 각 1개 · 모두 9개",
           font=font(23), fill=(110, 110, 110))
    d.line([(PAD, HEAD - 16), (W - PAD, HEAD - 16)], fill=(17, 17, 17), width=4)

    for i, (fn, name, qty, mat, col, memo, flip, elev) in enumerate(PARTS):
        c, r = i % COLS, i // COLS
        x = PAD + c * (TILE + PAD)
        y = HEAD + r * (TILE + CAP + PAD)

        path = os.path.join(PRINT_DIR, fn)
        if not os.path.exists(path):
            print(u"  없음:", fn)
            continue
        art = render(path, col, TILE, flip, elev)
        im.paste(art, (x, y), art)

        ty = y + TILE + 6
        d.text((x, ty), fn, font=font(22, True), fill=(17, 17, 17))
        d.text((x, ty + 30), u"%s  ×%d" % (name, qty), font=font(20), fill=(90, 90, 90))
        sw = 15
        d.rectangle([x, ty + 59, x + sw, ty + 59 + sw], fill=col, outline=(17, 17, 17))
        d.text((x + sw + 8, ty + 56), mat, font=font(19), fill=(60, 60, 60))
        if memo:
            d.text((x, ty + 81), memo, font=font(17), fill=(150, 150, 150))

    im.save(OUT)
    print(u"만들었습니다:", OUT)
    print(u"크기: %dx%d  %s bytes" % (im.size[0], im.size[1], format(os.path.getsize(OUT), ",")))


if __name__ == "__main__":
    main()
