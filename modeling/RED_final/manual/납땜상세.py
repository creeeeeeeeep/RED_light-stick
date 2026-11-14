# -*- coding: utf-8 -*-
u"""
납땜 상세도.

기존 선 그림은 보드를 통째로만 보여줘서 "어느 패드냐" 가 안 보인다.
여기서는 **납땜하는 면(부품이 붙어 있는 쪽)** 을 크게 그린다.

패드 배치는 실물 사진 기준이다 (2026-11-14 확인).
USB-C 를 위로 두고 부품 면을 보면
  왼쪽 열  위→아래 : 33 34 35 36 37 38 39 40 TX RX
  오른쪽 열 위→아래 : 5V G 3V3 7 6 5 4 3 2 1
  가운데 둥근 패드  : GND · 5V · Dout  (매트릭스 전원용. 크고 납땜하기 쉽다)

LED 면에서 보면 좌우가 뒤집힌다 — 제조사 핀아웃 그림이 그쪽이라 헷갈리기 쉽다.
"""

LEFTCOL  = [u"33", u"34", u"35", u"36", u"37", u"38", u"39", u"40", u"TX", u"RX"]
RIGHTCOL = [u"5V", u"G", u"3V3", u"7", u"6", u"5", u"4", u"3", u"2", u"1"]

RED, BLACK, YELLOW = u"#E34B4B", u"#2B2B2B", u"#F2C230"


def board():
    u"""납땜하는 면. 실제로 쓰는 패드 네 곳만 색으로 표시한다."""
    W, H = 440, 400
    x0, y0, bw, bh = 110, 40, 220, 300
    pitch = (bh - 34) / 9.0
    top = y0 + 17

    p = [u'<rect x="%d" y="%d" width="%d" height="%d" rx="9" fill="#fff" '
         u'stroke="#111" stroke-width="3"/>' % (x0, y0, bw, bh)]

    # USB-C (위쪽 가운데)
    p.append(u'<rect x="%d" y="%d" width="56" height="22" rx="4" fill="#e8e8e8" '
             u'stroke="#111" stroke-width="2.5"/>' % (x0 + bw / 2 - 28, y0 - 14))
    p.append(u'<text x="%d" y="%d" font-size="11" text-anchor="middle" fill="#666">USB-C</text>'
             % (x0 + bw / 2, y0 - 20))

    # RESET · BOOT
    for cx, nm in ((x0 + 36, u"RESET"), (x0 + bw - 36, u"BOOT")):
        p.append(u'<rect x="%d" y="%d" width="26" height="26" rx="4" fill="#f2f2f0" '
                 u'stroke="#111" stroke-width="2"/>' % (cx - 13, y0 + 16))
        p.append(u'<text x="%d" y="%d" font-size="9" text-anchor="middle" fill="#888">%s</text>'
                 % (cx, y0 + 12, nm))

    # 가운데 칩
    p.append(u'<rect x="%d" y="%d" width="76" height="76" rx="4" fill="#f3f3f1" '
             u'stroke="#ccc" stroke-width="2" transform="rotate(45 %d %d)"/>'
             % (x0 + bw / 2 - 38, y0 + 150, x0 + bw / 2, y0 + 188))
    p.append(u'<text x="%d" y="%d" font-size="10" text-anchor="middle" fill="#aaa">ESP32-S3</text>'
             % (x0 + bw / 2, y0 + 192))

    def pad(cx, cy, name, color=None, r=7.0):
        out = [u'<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="#111" '
               u'stroke-width="%.1f"/>'
               % (cx, cy, r + (1.5 if color else 0), color or u"#fff", 3 if color else 2)]
        return out

    # ---- 가장자리 두 열 ----
    for i, nm in enumerate(LEFTCOL):
        cy = top + i * pitch
        p += pad(x0 + 15, cy, nm)
        p.append(u'<text x="%.1f" y="%.1f" font-size="11" fill="#999">%s</text>'
                 % (x0 + 28, cy + 4, nm))

    use = {u"G": BLACK, u"1": YELLOW}
    for i, nm in enumerate(RIGHTCOL):
        cy = top + i * pitch
        col = use.get(nm)
        p += pad(x0 + bw - 15, cy, nm, col)
        p.append(u'<text x="%.1f" y="%.1f" font-size="11" text-anchor="end" '
                 u'font-weight="%s" fill="%s">%s</text>'
                 % (x0 + bw - 28, cy + 4, u"800" if col else u"500",
                    u"#111" if col else u"#999", nm))
        if col:
            lx = x0 + bw + 30
            p.append(u'<path d="M%.1f %.1f H%.1f" stroke="%s" stroke-width="3.5" '
                     u'stroke-linecap="round"/>' % (x0 + bw - 15, cy, lx, col))
            label = u"GND" if nm == u"G" else u"SIG"
            p.append(u'<text x="%.1f" y="%.1f" font-size="14" font-weight="800" fill="%s">%s</text>'
                     % (lx + 7, cy + 5, col, label))

    # ---- 가운데 둥근 패드 (전원) ----
    mx = x0 + 62
    for k, (nm, col) in enumerate(((u"GND", BLACK), (u"5V", RED), (u"Dout", None))):
        cy = top + (3 + k) * pitch
        p += pad(mx, cy, nm, col, r=8.5)
        p.append(u'<text x="%.1f" y="%.1f" font-size="12" font-weight="%s" fill="%s">%s</text>'
                 % (mx + 15, cy + 4, u"800" if col else u"500",
                    u"#111" if col else u"#999", nm))
        if col:
            p.append(u'<path d="M%.1f %.1f H%.1f" stroke="%s" stroke-width="3.5" '
                     u'stroke-linecap="round"/>' % (mx, cy, x0 - 34, col))
            p.append(u'<text x="%.1f" y="%.1f" font-size="14" font-weight="800" '
                     u'text-anchor="end" fill="%s">%s</text>'
                     % (x0 - 41, cy + 5, col, nm))

    p.append(u'<text x="%d" y="%d" font-size="14" font-weight="800" text-anchor="middle">'
             u'납땜하는 면 (부품이 붙어 있는 쪽)</text>' % (W / 2, y0 + bh + 34))
    p.append(u'<text x="%d" y="%d" font-size="11" text-anchor="middle" fill="#888">'
             u'LED 면에서 보면 좌우가 뒤집힌다</text>' % (W / 2, y0 + bh + 52))

    return (u'<svg class="bd" viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" '
            u'font-family="Noto Sans KR, Malgun Gothic, sans-serif">%s</svg>'
            % (W, H, u"".join(p)))


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
