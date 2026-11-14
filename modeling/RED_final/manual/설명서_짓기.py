# -*- coding: utf-8 -*-
"""
이케아식 조립 설명서를 짓는다.

그림은 기존 설명서에서 그대로 가져온다 — 실제 STL 로 뽑은 선 그림이라
다시 그릴 이유가 없다. 바뀌는 것은 배치다.

이케아 설명서의 규칙을 따른다.
  - 문장을 쓰지 않는다. 번호 · 글자 · 화살표 · 기호로 말한다.
  - 부품표를 먼저 한 쪽 통째로 보여준다.
  - 한 쪽에 한두 단계만 크게.
  - 글자는 틀리면 다치는 곳에만 남긴다 (배선, 길이, 각도).
"""
import io, re, base64, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 납땜상세

# 그림 원본(옛 설명서). 출력과 같은 파일을 가리키면 한 번 짓고 나서 다시 못 짓는다.
SRC = os.path.join(HERE, "그림원본.html")
OUT = os.path.join(HERE, u"RED_응원봉_조립설명서.html")

raw = io.open(SRC, encoding="utf-8").read()
imgs = []
for m in re.finditer(r'<img[^>]*?>', raw):
    tag = m.group(0)
    src = re.search(r'src="(data:image/png;base64,[^"]+)"', tag)
    if src:
        imgs.append(src.group(1))
assert len(imgs) == 24, len(imgs)

# 그림 번호 (추출 순서 그대로)
COVER, DONE = imgs[0], imgs[23]
PART = {k: imgs[1 + i] for i, k in enumerate("ABCDEFGH")}
ELEC = {"board": imgs[9], "usb": imgs[10], "sw": imgs[11]}
STEP = {1: (imgs[12], imgs[13]), 2: imgs[14], 3: imgs[15], 4: imgs[16], 5: imgs[17],
        6: imgs[18], 7: imgs[19], 8: imgs[20], 9: imgs[21], 10: imgs[22]}

PART_NAME = {"A": u"손잡이", "B": u"트레이", "C": u"뚜껑", "D": u"링",
             "E": u"보드 받침", "F": u"왕관", "G": u"돔", "H": u"십자"}

# ---- 기호 (선으로만 그린다) ----
def sym(body, vb="0 0 48 48"):
    return (u'<svg class="sym" viewBox="%s" fill="none" stroke="#111" '
            u'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">%s</svg>' % (vb, body))

GLUE = sym(u'<path d="M19 4h10v6l5 7v25a2 2 0 0 1-2 2H16a2 2 0 0 1-2-2V17l5-7V4z"/>'
           u'<path d="M14 24h20"/><path d="M24 2v2"/>')
IRON = sym(u'<path d="M6 40l9-9"/><path d="M14 30l10-10 8 8-10 10z"/>'
           u'<path d="M30 16l8-8 4 4-8 8z"/><path d="M8 42l2-6 4 4z" fill="#111"/>')
WIRE = sym(u'<path d="M4 24c6-10 12 10 18 0s12-10 18 0"/><path d="M4 34h40"/>')
TOOL = sym(u'<circle cx="24" cy="24" r="13"/><path d="M24 11v26M11 24h26"/>'
           u'<path d="M24 4v6M24 38v6M4 24h6M38 24h6"/>')
CABLE = sym(u'<rect x="6" y="19" width="16" height="10" rx="3"/>'
            u'<path d="M22 24h10"/><path d="M32 16h10v16H32z"/>')
TURN = sym(u'<path d="M38 24a14 14 0 1 1-6-11.5"/><path d="M38 8v9h-9"/>')
OK = sym(u'<path d="M10 25l9 9 19-20"/>')
NO = sym(u'<circle cx="24" cy="24" r="17"/><path d="M12 12l24 24"/>')

def page(inner, cls=""):
    return u'<section class="page %s">%s</section>' % (cls, inner)

def shot(src, alt=u"", cls=u""):
    return u'<img class="%s" src="%s" alt="%s">' % (cls, src, alt)

# ---------------------------------------------------------------- 표지
cover = page(
    u'<div class="cover">'
    u'  <div class="cover-txt">'
    u'    <div class="brand">RED</div>'
    u'    <h1>응원봉</h1>'
    u'    <div class="sub">v23 · v24</div>'
    u'    <div class="badges"><span class="badge">10</span>'
    u'      <span class="bl">단계</span></div>'
    u'    <div class="noscrew">'
    + NO + u'<b>나사 없음</b></div>'
    u'  </div>'
    + shot(COVER, u"완성", "cover-img") +
    u'</div>', "cover-page")

# ---------------------------------------------------------------- 부품
cells = u"".join(
    u'<figure class="part"><img src="%s" alt="%s">'
    u'<figcaption><span class="L">%s</span><span class="n">1×</span></figcaption>'
    u'<div class="pn">%s</div></figure>' % (PART[k], PART_NAME[k], k, PART_NAME[k])
    for k in "ABCDEFGH")

elec = u"".join(
    u'<figure class="part elec"><img src="%s" alt="%s">'
    u'<figcaption><span class="n">1×</span></figcaption><div class="pn">%s</div></figure>' % (s, n, n)
    for s, n in [(ELEC["board"], u"LED 보드"), (ELEC["usb"], u"USB-C 단자"), (ELEC["sw"], u"스위치")])

tools = u"".join(u'<div class="tool">%s<span>%s</span></div>' % (ic, nm) for ic, nm in
                 [(IRON, u"납땜 인두"), (WIRE, u"전선 4가닥"), (GLUE, u"본드"),
                  (TOOL, u"돌리개"), (CABLE, u"USB-C 케이블")])

parts = page(
    u'<h2 class="ph">부품</h2>'
    u'<div class="grid8">%s</div>'
    u'<h2 class="ph">전자</h2>'
    u'<div class="grid3">%s</div>'
    u'<h2 class="ph">준비물</h2>'
    u'<div class="tools">%s</div>' % (cells, elec, tools))

# ---------------------------------------------------------------- 경고
warn = page(
    u'<div class="warn">'
    u'  <div class="warnmark">!</div>'
    u'  <div class="warnbody">'
    u'    <p class="big">조립 전에 펌웨어를 굽는다.</p>'
    u'    <p class="small">조립하면 보드의 USB 단자를 쓸 수 없다.</p>'
    u'    <div class="warnrow">' + CABLE + u'<span class="arw">→</span>'
    + shot(ELEC["board"], u"보드", "warnimg") + u'</div>'
    u'  </div>'
    u'</div>'
    u'<div class="legend"><span class="sw"></span>노란색 = 이번에 끼우는 것</div>', "warn-page")

# ---------------------------------------------------------------- 단계
def step(n, body, note=u"", cls=u""):
    return (u'<div class="step %s"><div class="num">%d</div>'
            u'<div class="art">%s</div>%s</div>'
            % (cls, n, body, (u'<div class="note">%s</div>' % note) if note else u""))

s1 = step(1,
    shot(STEP[1][0], u"USB 단자 납땜", "half") + shot(STEP[1][1], u"스위치 납땜", "half"),
    u'<table class="wire">'
    u'<tr><td class="k">USB-C</td><td class="v">V</td><td class="v">G</td><td class="len">12 cm</td></tr>'
    u'<tr><td class="k">스위치</td><td class="v" colspan="2">같은 쪽 다리 2개</td><td class="len">8 cm</td></tr>'
    u'</table>')

s2 = step(2, shot(STEP[2], u"트레이에 USB 단자", "wide"))
s3 = step(3, shot(STEP[3], u"스위치", "wide"))
s4 = step(4, shot(STEP[4], u"뚜껑", "wide"))
s5 = step(5, shot(STEP[5], u"손잡이", "tall"))
s6 = step(6, shot(STEP[6], u"링", "tall"),
          u'<div class="icons">%s<b>조임</b>%s<b>케이블 꽂은 채</b></div>' % (TURN, CABLE))
s7 = step(7, shot(STEP[7], u"받침과 보드", "tall"),
          u'<table class="wire">'
          u'<tr><td class="k">V</td><td class="ar">→</td><td class="v">5V</td></tr>'
          u'<tr><td class="k">G</td><td class="ar">→</td><td class="v">GND</td></tr>'
          u'<tr><td class="k">스위치</td><td class="ar">→</td><td class="v">GPIO1 · GND</td></tr>'
          u'</table>')
# ---- 7 뒤에 납땜 상세 한 쪽 ----
solder = page(
    u'<h2 class="ph">납땜 자리</h2>'
    u'<div class="bdrow">%s</div>'
    u'<table class="wire big">'
    u'<tr><td class="k">USB-C <b>V</b></td><td class="ar">&rarr;</td>'
    u'<td class="v"><span class="dot d-r"></span>5V</td>'
    u'<td class="pos">가운데 둥근 패드</td></tr>'
    u'<tr><td class="k">USB-C <b>G</b></td><td class="ar">&rarr;</td>'
    u'<td class="v"><span class="dot d-k"></span>GND</td>'
    u'<td class="pos">그 바로 위 둥근 패드</td></tr>'
    u'<tr><td class="k">스위치</td><td class="ar">&rarr;</td>'
    u'<td class="v"><span class="dot d-y"></span>1</td>'
    u'<td class="pos">오른쪽 열 맨 아래</td></tr>'
    u'<tr><td class="k">스위치</td><td class="ar">&rarr;</td>'
    u'<td class="v"><span class="dot d-k"></span>G</td>'
    u'<td class="pos">오른쪽 열 위에서 2번째</td></tr>'
    u'</table>'
    u'<p class="hint">전원은 가운데 둥근 패드로 간다 — 크고 납땜하기 쉽다. '
    u'가장자리 <b>5V</b>·<b>G</b> 와 헷갈리지 않도록.</p>'
    % 납땜상세.board())

switch = page(
    u'<h2 class="ph">스위치 다리 고르기</h2>'
    u'<div class="swrow">%s</div>'
    u'<div class="checkbox">'
    u'<p class="big2">확인</p>'
    u'<p class="mono">BTN</p>'
    u'<table class="wire"><tr><td class="k">안 누름</td><td class="v">1</td></tr>'
    u'<tr><td class="k">누른 채</td><td class="v">0</td></tr></table>'
    u'<p class="hint">바뀌지 않으면 한 짝에서 두 개를 쓴 것이다 — 다른 다리로 옮긴다.</p>'
    u'</div>' % 납땜상세.switch_detail())

s8 = step(8, shot(STEP[8], u"왕관", "tall"), u'<div class="icons">%s<b>본드</b></div>' % GLUE)
s9 = step(9, shot(STEP[9], u"돔", "tall"),
          u'<div class="icons">%s<b>30°</b>%s<b>본드</b></div>' % (TURN, GLUE))
s10 = step(10, shot(STEP[10], u"십자", "tall"), u'<div class="icons">%s<b>본드</b></div>' % GLUE)

pages = [page(s1, "p-1"), switch, page(s2 + s3, "p-2"), page(s4 + s5, "p-2"),
         page(s6 + s7, "p-2"), solder, page(s8 + s9, "p-2"), page(s10, "p-1")]

# ---------------------------------------------------------------- 확인
checks = [u"케이블이 끝까지 꽂힌다", u"꽂으면 불이 켜진다", u"버튼이 딸깍 되돌아온다",
          u"흔들어도 덜그럭거리지 않는다", u"십자가 이름판과 같은 쪽"]
check = page(
    u'<div class="done">'
    + shot(DONE, u"완성", "doneimg") +
    u'  <ul class="checks">%s</ul>'
    u'</div>' % u"".join(u'<li>%s<span>%s</span></li>' % (OK, c) for c in checks), "done-page")

CSS = u"""
:root{--ink:#111;--y:#FFD84D;--line:#111;--mut:#777}
@page{size:A4;margin:12mm}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:#fff;color:var(--ink);
  font-family:"Noto Sans KR","Malgun Gothic",system-ui,sans-serif;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}
img{max-width:100%;display:block}
.sym{width:34px;height:34px;flex:none}
.page{width:186mm;min-height:262mm;margin:0 auto;padding:6mm 0;
  display:flex;flex-direction:column;gap:7mm;page-break-after:always;break-after:page}
.page:last-child{page-break-after:auto;break-after:auto}

/* 표지 */
.cover-page{justify-content:center}
.cover{display:grid;grid-template-columns:1fr auto;gap:10mm;align-items:center}
.brand{font-size:60px;font-weight:900;letter-spacing:-2px;line-height:1}
h1{font-size:44px;margin:2px 0 0;font-weight:800;letter-spacing:-1px}
.sub{color:var(--mut);font-size:15px;margin-top:6px}
.badges{display:flex;align-items:baseline;gap:8px;margin-top:22px}
.badge{display:inline-grid;place-items:center;width:64px;height:64px;border-radius:50%;
  background:var(--y);font-size:30px;font-weight:900}
.bl{font-size:17px;font-weight:700}
.noscrew{display:flex;align-items:center;gap:9px;margin-top:20px;font-size:17px}
.cover-img{width:62mm}

/* 부품표 */
.ph{font-size:15px;margin:0;padding-bottom:3px;border-bottom:2.5px solid var(--line);
  letter-spacing:2px}
.grid8{display:grid;grid-template-columns:repeat(4,1fr);gap:5mm}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:5mm}
.part{margin:0;border:2px solid var(--line);border-radius:3px;padding:3mm;text-align:center}
.part img{height:26mm;object-fit:contain;margin:0 auto}
.part figcaption{display:flex;justify-content:space-between;align-items:center;margin-top:2mm}
.L{display:grid;place-items:center;width:26px;height:26px;background:var(--y);
  border-radius:50%;font-weight:900;font-size:15px}
.n{font-weight:800;font-size:15px}
.pn{font-size:11px;color:var(--mut);margin-top:1mm}
.elec img{height:22mm}
.elec figcaption{justify-content:flex-end}
.tools{display:flex;gap:7mm;flex-wrap:wrap}
.tool{display:flex;flex-direction:column;align-items:center;gap:4px;font-size:11px;width:24mm;text-align:center}

/* 경고 */
.warn-page{justify-content:center}
.warn{display:flex;gap:6mm;border:3px solid var(--line);border-radius:4px;padding:7mm;align-items:flex-start}
.warnmark{display:grid;place-items:center;width:52px;height:52px;flex:none;
  background:var(--y);border-radius:50%;font-size:34px;font-weight:900;line-height:1}
.big{font-size:22px;font-weight:800;margin:0}
.small{color:var(--mut);margin:3mm 0 0;font-size:13px}
.warnrow{display:flex;align-items:center;gap:5mm;margin-top:5mm}
.arw{font-size:26px}
.warnimg{width:34mm}
.legend{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--mut)}
.legend .sw{width:16px;height:16px;background:var(--y);border:1.5px solid var(--line);border-radius:2px}

/* 단계 */
.step{display:flex;flex-direction:column;gap:3mm;flex:1;min-height:0}
.num{display:grid;place-items:center;width:46px;height:46px;flex:none;
  background:var(--y);border-radius:50%;font-size:25px;font-weight:900}
.art{display:flex;gap:5mm;justify-content:center;align-items:center;flex:1;min-height:0}
.art img{max-width:100%;width:auto;object-fit:contain}
.art img.wide{max-height:92mm}
.art img.tall{max-height:118mm}
.art img.half{max-height:62mm;max-width:48%}
.p-1 .art img.tall,.p-1 .art img.wide{max-height:170mm}
.p-1 .art img.half{max-height:105mm}
.note{display:flex;justify-content:center}
.icons{display:flex;align-items:center;gap:9px;font-size:15px}
.icons b{margin-right:7px}
table.wire{border-collapse:collapse;font-size:14px}
table.wire td{border:2px solid var(--line);padding:2mm 4mm;text-align:center}
table.wire .k{background:#f3f3f1;font-weight:800}
table.wire .v{font-weight:800;font-family:Consolas,monospace}
table.wire .len{background:var(--y);font-weight:800}
table.wire .ar{border:0;padding:0 3mm;font-size:17px}

/* 납땜 상세 */
.bdrow{display:flex;gap:6mm;justify-content:center;align-items:flex-start}
.bd{width:124mm;height:auto}
.sw{width:92mm;height:auto}
.swrow{display:flex;justify-content:center}
table.wire.big td{padding:2.5mm 5mm;font-size:15px}
table.wire .pos{background:#f8f8f6;color:#666;font-weight:500;font-size:12px}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;
  border:1.5px solid #111;vertical-align:-1px}
.dot.d-r{background:#E34B4B}.dot.d-k{background:#2B2B2B}.dot.d-y{background:#F2C230}
.hint{font-size:12px;color:#777;margin:3mm 0 0;text-align:center}
.checkbox{border:2.5px solid #111;border-radius:4px;padding:5mm;display:flex;
  flex-direction:column;align-items:center;gap:2mm;max-width:92mm;margin:0 auto}
.big2{font-size:17px;font-weight:800;margin:0}
.mono{font-family:Consolas,monospace;font-size:19px;font-weight:800;margin:0;
  background:var(--y);padding:1mm 5mm;border-radius:3px}
table.wire{margin:0 auto}

/* 확인 */
.done-page{justify-content:center}
.done{display:grid;grid-template-columns:auto 1fr;gap:9mm;align-items:center}
.doneimg{width:56mm}
.checks{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:4mm}
.checks li{display:flex;align-items:center;gap:9px;font-size:15px}

@media screen{
  body{background:#e9e9e6;padding:10px 0}
  .page{background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.18);margin-bottom:12px;
    padding:10mm;min-height:auto}
}
@media (max-width:820px){
  .page{width:auto;padding:14px}
  .grid8{grid-template-columns:repeat(2,1fr)}
  .grid3{grid-template-columns:repeat(2,1fr)}
  .cover,.done{grid-template-columns:1fr}
  .art{flex-direction:column}
  .art img.wide,.art img.tall,.art img.half{max-height:none;width:100%}
}
"""

html = (u'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        u'<meta name="viewport" content="width=device-width,initial-scale=1">'
        u'<title>RED 응원봉 조립 설명서</title><style>%s</style></head><body>%s</body></html>'
        % (CSS, cover + parts + warn + u"".join(pages) + check))

io.open(OUT, "w", encoding="utf-8").write(html)
print("지었습니다:", OUT)
print("크기: %s bytes" % format(os.path.getsize(OUT), ","))
