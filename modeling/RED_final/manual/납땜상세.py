# -*- coding: utf-8 -*-
u"""
납땜 상세도.

보드 그림은 직접 그린다 — 기존 선 그림은 보드를 통째로만 보여줘서
"어느 패드냐" 가 안 보인다.

패드 순서는 제조사 핀아웃(ESP32-S3-Matrix) 기준이다.
  왼쪽 열 위→아래 : 5V · G · 3V3 · 7 · 6 · 5 · 4 · 3 · 2 · 1
  오른쪽 열 위→아래 : 33 · 34 · 35 · 36 · 37 · 38 · 39 · 40 · TX · RX
실크에 찍힌 숫자가 곧 GPIO 번호다.
"""

LEFT  = [u"5V", u"G", u"3V3", u"7", u"6", u"5", u"4", u"3", u"2", u"1"]
RIGHT = [u"33", u"34", u"35", u"36", u"37", u"38", u"39", u"40", u"TX", u"RX"]

USE = {u"5V": u"#E34B4B", u"G": u"#2B2B2B", u"1": u"#F2C230"}   # 쓰는 패드 → 전선 색


def board(front=True):
    u"""보드 한 면. front=False 면 좌우가 뒤집힌 뒷면(납땜하는 쪽)."""
    W, H = 250, 250
    x0, y0 = 30, 18
    bw, bh = 190, 214
    pitch = (bh - 26) / 9.0

    p = []
    p.append(u'<rect x="%d" y="%d" width="%d" height="%d" rx="10" '
             u'fill="#fff" stroke="#111" stroke-width="3"/>' % (x0, y0, bw, bh))

    # USB-C 셸 (위쪽 가운데)
    p.append(u'<rect x="%d" y="%d" width="46" height="15" rx="6" fill="#ddd" '
             u'stroke="#111" stroke-width="2.5"/>' % (x0 + bw / 2 - 23, y0 - 7))
    p.append(u'<text x="%d" y="%d" font-size="10" text-anchor="middle" fill="#666">USB-C</text>'
             % (x0 + bw / 2, y0 - 12))

    # 8x8 매트릭스는 앞면에만
    if front:
        g0x, g0y, cell = x0 + 42, y0 + 36, 13.2
        for r in range(8):
            for c in range(8):
                p.append(u'<rect x="%.1f" y="%.1f" width="10" height="10" rx="1.6" '
                         u'fill="#fff" stroke="#bbb" stroke-width="1.4"/>'
                         % (g0x + c * cell, g0y + r * cell))
    else:
        p.append(u'<rect x="%d" y="%d" width="106" height="74" rx="4" fill="#f3f3f1" '
                 u'stroke="#bbb" stroke-width="2"/>' % (x0 + 42, y0 + 70))
        p.append(u'<text x="%d" y="%d" font-size="11" text-anchor="middle" fill="#999">'
                 u'ESP32-S3</text>' % (x0 + 95, y0 + 112))

    def column(labels, side_left, flip):
        u"""side_left: 그림에서 왼쪽에 그릴지. flip: 라벨을 오른쪽 열 것으로 바꿀지."""
        out = []
        px = x0 + 13 if side_left else x0 + bw - 13
        for i, name in enumerate(labels):
            cy = y0 + 13 + i * pitch
            col = USE.get(name)
            r = 7.5 if col else 6
            out.append(u'<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="#111" '
                       u'stroke-width="%.1f"/>'
                       % (px, cy, r, col if col else u"#fff", 3 if col else 2))
            tx = px + (15 if side_left else -15)
            anc = u"start" if side_left else u"end"
            out.append(u'<text x="%.1f" y="%.1f" font-size="11" text-anchor="%s" '
                       u'font-weight="%s" fill="%s">%s</text>'
                       % (tx, cy + 4, anc, u"800" if col else u"500",
                          u"#111" if col else u"#999", name))
            if col:
                # 바깥으로 빼는 지시선
                lx = x0 - 16 if side_left else x0 + bw + 16
                out.append(u'<path d="M%.1f %.1f H%.1f" stroke="%s" stroke-width="3.5" '
                           u'stroke-linecap="round"/>' % (px, cy, lx, col))
                out.append(u'<circle cx="%.1f" cy="%.1f" r="3" fill="%s"/>' % (lx, cy, col))
        return u"".join(out)

    if front:
        p.append(column(LEFT, True, False))
        p.append(column(RIGHT, False, True))
    else:
        # 뒤집으면 왼쪽 열이 오른쪽으로 온다
        p.append(column(RIGHT, True, False))
        p.append(column(LEFT, False, True))

    cap = u"앞면 (LED)" if front else u"뒷면 (납땜하는 쪽)"
    p.append(u'<text x="%d" y="%d" font-size="13" font-weight="800" text-anchor="middle">%s</text>'
             % (x0 + bw / 2, y0 + bh + 22, cap))
    return (u'<svg class="bd" viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" '
            u'font-family="Noto Sans KR, Malgun Gothic, sans-serif">%s</svg>'
            % (W, H + 16, u"".join(p)))


def switch_detail():
    u"""
    택트 스위치 다리 고르기.

    6x6 택트 스위치는 다리 4개가 두 짝으로 묶여 있다. 한 짝끼리는 **안에서
    이미 붙어 있고**, 누르면 두 짝이 이어진다. 그래서 한 짝에서 하나씩,
    둘로 갈라서 써야 한다. 한 짝에서 두 개를 쓰면 늘 이어진 상태가 된다.

    어느 다리가 한 짝인지는 스위치마다 다르게 보인다. 눈으로 가리지 말고
    아래 BTN 으로 확인하는 것이 확실하다.
    """
    return (u'<svg class="sw" viewBox="0 0 320 200" xmlns="http://www.w3.org/2000/svg" '
            u'font-family="Noto Sans KR, Malgun Gothic, sans-serif">'
            u'<rect x="105" y="42" width="110" height="110" rx="7" fill="#fff" '
            u'stroke="#111" stroke-width="3"/>'
            u'<circle cx="160" cy="97" r="25" fill="#f3f3f1" stroke="#111" stroke-width="3"/>'
            u'<rect x="82" y="60" width="24" height="12" fill="#fff" stroke="#111" stroke-width="2.5"/>'
            u'<rect x="82" y="122" width="24" height="12" fill="#fff" stroke="#111" stroke-width="2.5"/>'
            u'<rect x="214" y="60" width="24" height="12" fill="#fff" stroke="#111" stroke-width="2.5"/>'
            u'<rect x="214" y="122" width="24" height="12" fill="#fff" stroke="#111" stroke-width="2.5"/>'
            u'<path d="M94 72 V122" stroke="#E34B4B" stroke-width="3" stroke-dasharray="5 4"/>'
            u'<path d="M226 72 V122" stroke="#E34B4B" stroke-width="3" stroke-dasharray="5 4"/>'
            u'<text x="52" y="100" font-size="11" text-anchor="middle" fill="#E34B4B" '
            u'font-weight="700">한 짝</text>'
            u'<text x="268" y="100" font-size="11" text-anchor="middle" fill="#E34B4B" '
            u'font-weight="700">한 짝</text>'
            u'<text x="160" y="24" font-size="13" text-anchor="middle" font-weight="800">'
            u'한 짝에서 하나씩, 둘로 갈라서</text>'
            u'<text x="160" y="178" font-size="11.5" text-anchor="middle" fill="#666">'
            u'붉은 점선끼리는 안에서 이미 붙어 있다 — 그 둘만 쓰면 늘 이어진다</text>'
            u'</svg>')
