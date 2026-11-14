"""
red_v23.py — 손잡이 + 캐리어(트레이/뚜껑) + 조임 링  (독립 스크립트)

왜 다시 짰나
  v20~v22 캐리어는 'Ø14 구멍 속에 부품을 끝에서 밀어 넣는' 구조였다.
  안이 안 보이고, 치수가 0.3 만 틀려도 안 들어가고, 무엇이 걸리는지 알 수 없었다.
  → v23 은 '도시락 통' 이다.

  트레이(07a) : 눕혀 놓고 USB · 스위치 · 전선을 전부 위에서 내려놓는다. 다 보인다.
  뚜껑 (07b) : 덮는다. USB 와 스위치가 눌린다.
  손잡이(05) : 구멍 뒤쪽이 평평(D자) → 한 방향으로만 들어간다. 바닥은 원뿔 자리.
  링   (07c) : 위에서 돌려 조인다. 캐리어가 위·아래 원뿔 사이에 물려 유격이 0 이 된다.

고정 원리 (본드 없음 · 치수가 조금 틀려도 링이 흡수한다)
  케이블 뽑는 힘 → 셸(8.83)이 손잡이 바닥 구멍(8.50)을 못 지나간다
  케이블 꽂는 힘 → 셸 뒷면 → 트레이 기둥 → 링 나사 → 손잡이
  버튼 누르는 힘 → 스위치 밑 레일 → 트레이 → 위·아래 원뿔 → 손잡이

v22 까지의 실수 (이번에 고친 것)
  · '앞코 모따기' 가 실제로는 테두리만 남기고 속을 파는 카운터보어였다 → 진짜 모따기
  · 방향 키 리브가 홈에 0.05mm 만 물렸다 → D자 구멍으로 대체
  · 캐리어가 위로 밀리는 것을 막는 것이 없었다 (케이블을 꽂으면 캐리어가 올라간다) → 링
  · 캐리어가 구멍 안에서 ±0.35 놀았다 → 흔들 때 스위치가 플런저를 칠 수 있었다 → 원뿔 물림
  · 바닥이 2.8mm 라 C타입 플러그가 3.85mm 밖에 안 물렸다 → 2.0mm
  · USB 포켓 입구가 베드 쪽이라 코끼리발로 좁아졌다 → 포켓이 위를 보고 인쇄된다
"""
import numpy as np, math, os, trimesh
from shapely.geometry import Polygon as SPoly, box as sbox, Point as SPt
from shapely.affinity import scale as sscale

OUT = "/home/claude/v23"; os.makedirs(OUT, exist_ok=True)
SEG = 160

# ═══════════ 부품 치수 (실측 · 공칭) ═══════════
SK_SW, SK_SH, SK_SL = 8.90, 3.10, 8.80      # USB-C 금속 셸 폭·높이·깊이   ★ 2026-11-14 정수 실측
SK_WMAX = 9.0                               # 납땜 귀 포함 가장 넓은 곳
SK_PW, SK_PT, SK_PL = 9.00, 1.60, 14.00     # 브레이크아웃 PCB : 폭 9.0 · 두께 1.6 · 셸 앞끝~기판 끝 14
#   ★ 2026-11-14 옆모습 사진으로 확정 : 기판이 셸 '뒤' 에, 셸 두께의 '가운데' 에 꽂혀 있다 (끼움형). 전체 높이 = 셸 3.1.
#     기판은 셸보다 넓고(9.0) 셸 밑으로는 안 들어간다. 셸 뒤쪽 면에 납땜 귀(약 0.5)가 튀어나와 있다.
#     1차 : 좁은 기판이 기둥 사이(7.8)로 빠진다고 가정 → 기판이 걸림.  2차 : 기판이 셸 밑에 붙었다고 가정 → 틀림.
#     → 3차는 '셸 앞 5.5mm 만 물고' 나머지는 전부 넉넉히 비운다. 기판 두께·위치·납땜이 달라도 상관없게.
SW_W, SW_DEEP, SW_STEM_H = 6.0, 3.8, 1.2    # 택트 스위치 6x6x5 : 몸통 3.8 + 돌기 1.2 · 다리 끝~끝 7.2
PLUG_W, PLUG_H = 8.34, 2.56                 # C타입 케이블 플러그

# ═══════════ 손잡이 ═══════════
HAND_R, BORE_R = 8.5, 7.0
HAND_TOP, HAND_BOT = -12.0, -63.0
BOT_TOT  = 2.0                              # 손잡이 바닥 두께
LIP_T    = 0.8                              # ★ 셸 앞을 막는 턱 두께 = 케이블이 덜 들어가는 양
#   2026-11-14 실물 : 케이블을 끝까지 꽂으면 금속이 1.91mm 남는다 → 셸 앞을 가리는 살은 1.91 보다 얇아야 한다.
#   이전 판은 싱크 1.0 + 벽 1.0 = 2.0 이었고, 케이블 몰딩이 싱크(13x7)에 안 들어가면 2.0 을 다 먹어 끝까지 안 꽂혔다.
#   → 싱크를 없앴다. 바닥은 평평하고, 셸이 바닥 속 주머니로 내려와 0.8mm 턱 바로 뒤에 선다. 몰딩 크기와 무관하다.
USB_OUT  = BOT_TOT - LIP_T - 0.1            # 셸이 캐리어 끝보다 더 나오는 길이 (1.1) → 손잡이 바닥 주머니로 들어간다
COL_TOP_R = 19.5
CROWN_BOT = -1.0                            # 왕관 밑면 = 손잡이 칼라 윗면
FLG_BOT   = CROWN_BOT - 3.2
LID_HW, LID_CR = 14.15, 8.0                 # 왕관 자리(29.0각)에 들어가는 플러그 28.3각
PLUG_TOP  = 1.8                             # ★ 2.6 → 1.8 : 보드 밑 부품과 간섭 여유 +0.8
MOUTH_Y   = 0.25                            # 바닥 구멍(=셸) 중심 높이

# ═══════════ 갇힌 버튼 (캘리브레이션 완료값 — 건드리지 말 것) ═══════════
SW_Z     = -22.0
SWF_Y    = 4.40                             # 스위치 몸통 윗면 (밑면 0.6 · 돌기 끝 5.6 은 그대로 → 손잡이·버튼 불변)
BTN_GAP, BTN_TRAV, BTN_BIAS = 0.50, 1.10, 0.30
PAD_UP, PAD_W, PAD_Z = 3.3, 14.0, 13.0
BZL_T, APER_D = 1.0, 6.0
NOSE_D   = APER_D - (BTN_GAP+0.10)*2
NOSE_OUT = 2.0
FLG_HW, FLG_T, PLG_D = 4.0, 1.1, 5.0

# ═══════════ 캐리어 ═══════════
CR_R   = 6.55                               # 구멍 7.0 − 0.45 (헐렁하게. 물림은 원뿔이 한다)
YS     = 2.0                                # 트레이/뚜껑 분할면 (셸 윗면 1.82 + 0.18)
YB     = -5.1                               # 트레이 등(평면) — 여기가 베드에 닿는다
D_GAP  = 0.20
D_FLAT = YB - D_GAP                         # 손잡이 구멍의 평면 (D자)
CR_BOT = HAND_BOT + BOT_TOT                 # -61.0
CR_TOP = -5.0
CH_BOT, CH_TOP = 1.0, 0.8                   # 캐리어 양끝 45도 모따기 = 원뿔 자리
SEAT_GAP = 0.03                             # 바닥 원뿔과의 틈 (사실상 닿는다)
SHL_HW   = SK_SW/2 + 0.20                   # 셸 자리 반폭 (9.3)
POC_HW   = SK_PW/2 + 0.20                   # 기판 자리 반폭 (9.4)
SEAT_L   = 5.5                              # 셸을 위아래로 무는 길이 (앞 5.5mm — 매끈한 부분만)
SEAT_Y   = MOUTH_Y - SK_SH/2 - 0.05         # 셸 밑면이 앉는 바닥 (셸 중심 = 손잡이 바닥 구멍 높이)
REL_Y    = MOUTH_Y - 2.45                   # 그 뒤 바닥 : 0.85 더 깊다 (납땜 귀 · 기판 밑 납땜 · 전선)
USB_Z0   = CR_BOT - USB_OUT                 # 셸 앞끝
STOP_Z   = USB_Z0 + SK_PL + 0.15            # 기판 뒤끝이 닿는 벽 (꽂는 힘)
STOP_T   = 1.6                              # 벽 두께
STOP_Y   = MOUTH_Y + 0.55                   # 벽 윗면 : 기판 두께의 대부분을 받고, 전선은 그 위로 넘어간다
TAIL_END = STOP_Z + STOP_T + 6.5
SW_SEAT  = SWF_Y - SW_DEEP                  # 스위치 밑면이 앉는 레일
CHAN_Y, CHAN_HI = 5.2, 5.72                 # 플런저 길 바닥 · 스위치 앞에서는 스템(5.6)보다 높게
PEG_Z = (-36.3, -31.0, -10.0)
EF    = 0.4                                 # 코끼리발 도피 모따기

# ═══════════ 조임 링 나사 (45도 사다리꼴 — 서포트 없이 뽑힌다) ═══════════
TH_P, TH_D, TH_CW = 2.4, 0.9, 0.3           # 피치 · 산 높이 · 산 끝 폭
TH_CLR  = 0.35                              # 반지름 틈
RING_RR = 7.55                              # 링 골 반지름
RING_RC = RING_RR + TH_D                    # 링 산 반지름 8.45
TH_RM   = RING_RR + TH_CLR                  # 손잡이 나사 안지름 7.90
TH_RJ   = RING_RC + TH_CLR                  # 손잡이 나사 골 8.80
TH_Z0   = -6.6                              # 손잡이 나사 시작 높이
FUN_Z0  = TH_Z0 - (TH_RM - BORE_R)          # 깔때기 (7.9 → 7.0)
RING_H  = 4.2
RING_ID = 5.6
RING_IN = 6.45                              # 링 밑 원뿔 입구 반지름
RING_ZB = CR_TOP - (RING_IN - (CR_R - CH_TOP)) + 0.02   # 원뿔이 캐리어 모따기에 닿는 높이

# ═══════════ 헬퍼 ═══════════
def vz(m):
    if m.is_volume:
        if m.volume < 0: m.invert()
        return m
    m.merge_vertices(); m.update_faces(m.nondegenerate_faces()); m.remove_unreferenced_vertices()
    trimesh.repair.fix_inversion(m); trimesh.repair.fix_normals(m); trimesh.repair.fill_holes(m)
    if m.volume < 0: m.invert()
    return m
def bez(p, n=70):
    p = np.array(p, float); t = np.linspace(0, 1, n)[:, None]
    return ((1-t)**3)*p[0] + 3*((1-t)**2)*t*p[1] + 3*(1-t)*t**2*p[2] + t**3*p[3]
def rev(prof, seg=SEG, lo=True, hi=True):
    P = np.asarray(prof, float); th = np.linspace(0, 2*np.pi, seg, endpoint=False)
    V = np.vstack([np.column_stack([r*np.cos(th), r*np.sin(th), np.full(seg, z)]) for r, z in P])
    K = len(P); F = []
    for k in range(K-1):
        for i in range(seg):
            j = (i+1) % seg
            F.append([k*seg+i, k*seg+j, (k+1)*seg+j]); F.append([k*seg+i, (k+1)*seg+j, (k+1)*seg+i])
    V = list(map(list, V))
    if lo:
        c = len(V); V.append([0, 0, P[0, 1]])
        for i in range(seg): F.append([c, (i+1) % seg, i])
    if hi:
        c = len(V); V.append([0, 0, P[-1, 1]]); b = (K-1)*seg
        for i in range(seg): F.append([c, b+i, b+(i+1) % seg])
    return vz(trimesh.Trimesh(np.array(V), np.array(F), process=True))
def tube_rev(loop, seg=SEG):
    L = np.asarray(loop, float)
    a = sum(L[i, 0]*L[(i+1) % len(L), 1] - L[(i+1) % len(L), 0]*L[i, 1] for i in range(len(L)))
    if a < 0: L = L[::-1]
    return rev(np.vstack([L, L[:1]]), seg, lo=False, hi=False)
def bx(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box((x1-x0, y1-y0, z1-z0)); b.apply_translation([(x0+x1)/2, (y0+y1)/2, (z0+z1)/2]); return b
def cyl(r, h, pos=(0, 0, 0), axis='z', n=96):
    c = trimesh.creation.cylinder(radius=r, height=h, sections=n)
    if axis == 'y': c.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]))
    c.apply_translation(pos); return c
def stad(w, d, r=None):
    if r is None: r = min(w, d)/2 - 0.15
    return sbox(-w/2, -d/2, w/2, d/2).buffer(-r, resolution=24).buffer(r, resolution=24)
def ext(poly, z0, z1):
    m = trimesh.creation.extrude_polygon(poly, z1-z0); m.apply_translation([0, 0, z0]); return vz(m)
def house(hw, zb, zs):
    return SPoly([(-hw, zb), (hw, zb), (hw, zs), (0.0, zs+hw), (-hw, zs)])
def yprism(poly, y0, y1):
    m = trimesh.creation.extrude_polygon(sscale(poly, 1.0, -1.0, origin=(0, 0)), y1-y0)
    m.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
    m.apply_translation([0, y0, SW_Z]); return vz(m)
def prism_x(poly_zy, x0, x1):
    """(z, y) 평면 다각형을 x 로 밀어낸다"""
    m = trimesh.creation.extrude_polygon(SPoly(poly_zy), x1-x0)
    m.apply_transform(np.array([[0, 0, 1, x0], [0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1.0]]))
    m.invert(); return vz(m)
def d2d(r):
    """뒤쪽이 평평한 D자 단면"""
    return SPt(0, 0).buffer(r, resolution=64).intersection(sbox(-r-1, D_FLAT, r+1, r+1))
def chamfer_end(m, z, c, r, up):
    """원기둥 끝의 진짜 45도 모따기. up=True 면 위쪽 끝"""
    s = 1 if up else -1
    return vz(m.difference(tube_rev([[r-c, z+s*0.02], [r+1, z+s*0.02], [r+1, z-s*(c+1)]])))
def helix(prof, za, zb, seg=120):
    """(r, dz) 단면을 나선으로 쓸어 만든 나사산. 위상은 전역 기준(z=0, θ=0)에 고정 → 암·수가 항상 맞물린다"""
    n = len(prof); k0 = math.floor(za/TH_P) - 1
    M = int(math.ceil(((zb-za)/TH_P + 3)*seg)); V = []; F = []
    for j in range(M+1):
        th = 2*math.pi*j/seg; zo = k0*TH_P + TH_P*j/seg
        for (r, dz) in prof: V.append([r*math.cos(th), r*math.sin(th), zo+dz])
    for j in range(M):
        for k in range(n):
            a, b = j*n+k, j*n+(k+1) % n; c, d = (j+1)*n+(k+1) % n, (j+1)*n+k
            F += [[a, b, c], [a, c, d]]
    for k in range(1, n-1):
        F.append([0, k+1, k]); F.append([M*n, M*n+k, M*n+k+1])
    return vz(trimesh.Trimesh(np.array(V), np.array(F), process=True))
def loft2(pa, za, pb, zb, n=96):
    """윤곽 pa(z=za) 와 pb(z=zb) 를 잇는 통 (모따기용). 중심에서 같은 각도로 점을 찍어 꼬이지 않는다"""
    from shapely.geometry import LineString
    def ring(p, z):
        return [[q.x, q.y, z] for q in (p.exterior.intersection(LineString([(0, 0), (60*math.cos(2*math.pi*k/n), 60*math.sin(2*math.pi*k/n))])) for k in range(n))]
    V = ring(pa, za) + ring(pb, zb); F = []
    for i in range(n):
        j = (i+1) % n; F += [[i, j, n+j], [i, n+j, n+i]]
    V += [[0, 0, za], [0, 0, zb]]
    for i in range(n):
        j = (i+1) % n; F += [[2*n, j, i], [2*n+1, n+i, n+j]]
    return vz(trimesh.Trimesh(np.array(V), np.array(F), process=True))
def rotz(m, deg):
    m = m.copy(); m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(deg), [0, 0, 1])); return m
def D(a, b): return vz(a.difference(b))
def U(a, b): return vz(a.union(b))
def I(a, b): return vz(a.intersection(b))
def save(m, name, expect=1):
    m = vz(m); cs = m.split(only_watertight=False)
    if len(cs) > expect:
        keep = [c for c in cs if abs(c.volume) > 0.5]
        if len(keep) == expect: m = trimesh.util.concatenate(keep)
    m.export(f"{OUT}/{name}.stl"); e = m.bounds[1]-m.bounds[0]
    nb = len(m.split(only_watertight=False))
    print(f"  {name:16s} {e[0]:5.1f} x {e[1]:5.1f} x {e[2]:5.1f}  {m.volume/1000:5.2f}cm3  wt={m.is_watertight}  "
          f"덩어리 {nb}{'' if nb == expect else '  ⚠ 예상 '+str(expect)}")
    return m

print("RED v23 — 손잡이 + 트레이 캐리어 + 조임 링\n")

# ═══════════════════ 05 손잡이 ═══════════════════
# 규칙 : 붙이는 것(union)을 전부 먼저, 파는 것(cut)을 전부 나중에, 떠 있는 버튼은 맨 마지막.
hp = np.vstack([
      [[HAND_R-1.2, HAND_BOT]],
      bez([[HAND_R-1.2, HAND_BOT], [HAND_R-0.2, HAND_BOT], [HAND_R, HAND_BOT+0.6], [HAND_R, HAND_BOT+1.8]], 14),
      [[HAND_R, HAND_TOP-4.0]],
      bez([[HAND_R, HAND_TOP-3.4], [HAND_R+0.6, HAND_TOP-2.2], [HAND_R+1.4, HAND_TOP-1.2], [HAND_R+2.2, HAND_TOP]], 12),
      [[COL_TOP_R, HAND_TOP+COL_TOP_R-(HAND_R+2.2)]], [[COL_TOP_R, CROWN_BOT]]])      # 칼라 밑면 정확히 45도
hand = rev(np.vstack([[[0, HAND_BOT]], hp, [[0, CROWN_BOT]]]))
# ── 겉 장식 홈 (받침·귀를 붙이기 전에 — 붙는 자리는 도로 메워진다) ──
for i in range(12):                                               # 세로 홈 장식
    a = 2*math.pi*i/12
    hand = D(hand, cyl(0.7, abs(HAND_TOP-HAND_BOT)*0.52,
                       ((HAND_R+0.45)*math.cos(a), (HAND_R+0.45)*math.sin(a), (HAND_TOP+HAND_BOT)/2-6)))
# ── 붙이기 ──
dia = trimesh.creation.box((8.4, 2.4, 8.4))                       # 다이아 문양
dia.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4, [0, 1, 0]))
dia.apply_translation([0, HAND_R-0.6, HAND_TOP-4.5]); hand = U(hand, dia)
Y_OUT  = HAND_R + PAD_UP
Y_BZL  = Y_OUT - BZL_T
Y_FLGF = Y_BZL - BTN_GAP
Y_FLGB = Y_FLGF - FLG_T
Y_FLOOR = Y_FLGB - BTN_TRAV
STEM_TOP = SWF_Y + SW_STEM_H
Y_TIP  = STEM_TOP - BTN_GAP + BTN_BIAS
pad = trimesh.creation.extrude_polygon(stad(PAD_W, PAD_Z, 3.0), PAD_UP+2.0)   # 버튼 받침
pad.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
pad.apply_translation([0, HAND_R-2.0, SW_Z]); hand = U(hand, pad)
_o = np.array(stad(PAD_W, PAD_Z, 3.0).exterior.coords)                       # 받침 밑면이 허공에 뜨지 않게 45도 쐐기
_o = _o[_o[:, 1] < -PAD_Z/2 + 3.0*(1-math.cos(math.pi/4)) + 0.01]
_w = np.vstack([[[x, Y_OUT, SW_Z+z] for x, z in _o], [[x, Y_OUT-7.5, SW_Z+z] for x, z in _o],
                [[x, Y_OUT-7.5, SW_Z+z-7.5] for x, z in _o]])
hand = U(hand, vz(trimesh.convex.convex_hull(_w)))
EAR_T, EAR_L, EAR_HW, EAR_HOLE_R, EAR_HOLE_Y = 6.4, 8.5, 4.6, 2.2, -12.9      # 스트랩 귀
e2d = sbox(-EAR_HW, -(HAND_R+EAR_L), EAR_HW, -HAND_R+3.4).buffer(-4.0, resolution=20).buffer(4.0, resolution=20)
hand = U(hand, ext(e2d, HAND_BOT, HAND_BOT+EAR_T))
hand = U(hand, ext(stad(LID_HW*2, LID_HW*2, LID_CR), CROWN_BOT-0.5, PLUG_TOP))  # 왕관에 끼우는 플러그
# ── 파기 ──
hand = D(hand, cyl(EAR_HOLE_R, EAR_T+8.0, (0, EAR_HOLE_Y, HAND_BOT+EAR_T/2)))
SEAT_R0 = CR_R - CH_BOT + SEAT_GAP                                # 바닥 원뿔 자리
bore = I(ext(d2d(BORE_R), CR_BOT, FUN_Z0+0.01),
         rev([[0, CR_BOT], [SEAT_R0, CR_BOT], [BORE_R+0.3, CR_BOT+BORE_R+0.3-SEAT_R0], [BORE_R+0.3, FUN_Z0+1], [0, FUN_Z0+1]]))
hand = D(hand, bore)                                              # D자 구멍 + 바닥 원뿔
hand = D(hand, rev([[0, FUN_Z0], [BORE_R, FUN_Z0], [TH_RM, TH_Z0], [TH_RM, PLUG_TOP+1], [0, PLUG_TOP+1]]))   # 깔때기 + 나사 안지름
groove = helix([[TH_RM-0.05, -(TH_CW/2+TH_D+0.05)], [TH_RJ, -TH_CW/2], [TH_RJ, TH_CW/2], [TH_RM-0.05, TH_CW/2+TH_D+0.05]],
               TH_Z0, PLUG_TOP+1)
hand = D(hand, I(groove, cyl(TH_RJ+1, PLUG_TOP+1-TH_Z0, (0, 0, (PLUG_TOP+1+TH_Z0)/2))))                      # 나사 골
hand = D(hand, tube_rev([[TH_RM-0.01, PLUG_TOP-1.0], [TH_RM+1.4, PLUG_TOP+0.4], [TH_RM-0.01, PLUG_TOP+0.4]]))  # 입구 모따기
_sh = stad(SK_SW+0.4, SK_SH+0.4, (SK_SH+0.4)/2-0.02)                 # 셸 주머니 9.3 x 3.5
_ap = stad(PLUG_W+0.16, PLUG_H+0.16, (PLUG_H+0.16)/2-0.02)           # 플러그 구멍 8.50 x 2.72
def _at(m): m.apply_translation([0, MOUTH_Y, 0]); return m
hand = D(hand, _at(ext(_sh, HAND_BOT+LIP_T, CR_BOT+0.05)))                                    # 셸 앞끝이 들어오는 주머니
hand = D(hand, _at(loft2(_sh, CR_BOT-0.6, _sh.buffer(0.6, resolution=24), CR_BOT+0.02)))      # 주머니 입구 모따기 (셸을 안내)
hand = D(hand, _at(ext(_ap, HAND_BOT-0.05, HAND_BOT+LIP_T+0.05)))                             # 플러그 구멍 (턱 0.8)
hand = D(hand, _at(loft2(_ap.buffer(0.3, resolution=24), HAND_BOT-0.01, _ap, HAND_BOT+0.3)))  # 바깥 모따기 (베드 쪽 코끼리발 · 플러그 안내)
hand = D(hand, yprism(house(FLG_HW+BTN_GAP, -(FLG_HW+BTN_GAP), 1.85), Y_FLOOR, Y_BZL+0.001))   # 버튼 걸림판 방
hand = D(hand, cyl(APER_D/2, BZL_T+4.0, (0, Y_BZL-0.5, SW_Z), axis='y'))                        # 베젤 구멍
PLG_Y1 = Y_FLOOR + 0.5                                            # 앞벽만 뚫는다 (뒤 관통 금지)
hand = D(hand, cyl(PLG_D/2+BTN_GAP, PLG_Y1, (0, PLG_Y1/2, SW_Z), axis='y'))
# ── 갇힌 버튼 본체 (맨 마지막) ──
btn = yprism(house(FLG_HW, -FLG_HW, 1.50), Y_FLGB, Y_FLGF)
_pr = np.array([[0, Y_TIP], [1.20, Y_TIP], [PLG_D/2, Y_TIP+1.30], [PLG_D/2, Y_FLGF], [NOSE_D/2, Y_FLGF],
                [NOSE_D/2, Y_OUT+NOSE_OUT-1.05], [NOSE_D/2-0.50, Y_OUT+NOSE_OUT-0.35],
                [max(NOSE_D/2-1.45, 0.2), Y_OUT+NOSE_OUT], [0, Y_OUT+NOSE_OUT]])
shaft = rev(_pr, 96)
shaft.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
shaft.apply_translation([0, 0, SW_Z])
btn = vz(trimesh.boolean.union([btn, vz(shaft)]))
hand_solid = hand
save(trimesh.util.concatenate([hand, btn]), "05_handle_RED", expect=2)

# ═══════════════════ 07a 트레이 ═══════════════════
CH_C = 3.71 - YB                                                   # 등 모서리 45도 (서포트 없이 눕혀 뽑기)
circ = SPt(0, 0).buffer(CR_R, resolution=64)
tray2d = circ.intersection(sbox(-10, YB, 10, YS)).intersection(
         SPoly([(0, -CH_C), (20, 20-CH_C), (20, 20), (-20, 20), (-20, 20-CH_C)]))
tray = ext(tray2d, CR_BOT, CR_TOP)
tray = D(tray, bx(-SHL_HW, SHL_HW, SEAT_Y, YS+1, CR_BOT-1, USB_Z0+SK_SL+0.3))                # 셸 자리 (앞 5.5mm 바닥에 앉는다)
tray = D(tray, bx(-POC_HW, POC_HW, REL_Y, YS+1, USB_Z0+SEAT_L, STOP_Z))                      # 셸 뒤쪽 + 기판 : 바닥을 비운다
tray = D(tray, bx(-POC_HW, POC_HW, STOP_Y, YS+1, STOP_Z-0.01, STOP_Z+STOP_T+0.01))           # 뒷벽 위 (전선이 넘어가는 길)
tray = D(tray, bx(-POC_HW, POC_HW, REL_Y, YS+1, STOP_Z+STOP_T, TAIL_END))                    # 전선 칸
tray = D(tray, bx(-3.0, 3.0, YB-1, REL_Y+0.01, TAIL_END-3.5, TAIL_END))                      # 전선이 등으로 내려가는 구멍
tray = D(tray, bx(-2.4, 2.4, YB-1, YB+2.0, TAIL_END-0.01, CR_TOP+1))                      # 등 쪽 전선 홈
tray = D(tray, bx(-3.5, 3.5, SW_SEAT, YS+1, SW_Z-3.5, SW_Z+3.5))                          # 스위치 자리
for sg in (1, -1):                                                                        # 다리 + 납땜한 전선이 떨어질 틈
    tray = D(tray, bx(min(sg*2.3, sg*4.4), max(sg*2.3, sg*4.4), YB-1, YS+1, SW_Z-3.7, SW_Z+3.7))
tray = D(tray, bx(-4.2, 4.2, YB-1, -1.6, SW_Z-4.5, SW_Z+4.5))                             # 스위치 밑 배선 공간
for z in PEG_Z:                                                                           # 뚜껑 맞춤 핀
    tray = U(tray, cyl(1.5, 1.8+0.4, (0, YS+0.9-0.2, z), axis='y', n=40))
tray = chamfer_end(tray, CR_BOT, CH_BOT, CR_R, up=False)
tray = chamfer_end(tray, CR_TOP, CH_TOP, CR_R, up=True)
for zc, s in ((CR_BOT, 1), (CR_TOP, -1)):                                                 # 베드 쪽 끝 모서리 (코끼리발 도피)
    tray = D(tray, prism_x([(zc-s*0.05, YB-0.05), (zc+s*EF, YB-0.05), (zc-s*0.05, YB+EF)], -8, 8))
tray = save(tray, "07a_tray_RED")

# ═══════════════════ 07b 뚜껑 ═══════════════════
xe = math.sqrt(CR_R**2 - YS**2)
lid2d = circ.intersection(sbox(-10, YS, 10, 10))
for sg in (1, -1):                                                                        # 베드 쪽 긴 모서리 (코끼리발 도피)
    lid2d = lid2d.difference(SPoly([(sg*(xe-EF), YS-0.1), (sg*(xe+0.5), YS-0.1), (sg*(xe+0.5), YS+EF+0.5)]))
lid = ext(lid2d, CR_BOT, CR_TOP)
lid = D(lid, prism_x([(CR_BOT-1, CHAN_Y), (SW_Z-6.5, CHAN_Y), (SW_Z-4.5, CHAN_HI), (SW_Z, CHAN_HI),
                      (SW_Z, 9), (CR_BOT-1, 9)], -2.9, 2.9))                              # 플런저가 지나갈 길
lid = D(lid, prism_x([(CR_BOT-0.5, 3.35), (CR_BOT+3.2, CHAN_Y), (CR_BOT+3.2, 9), (CR_BOT-0.5, 9)],
                     -2.9, 2.9))                                                          # 입구 경사 (플런저를 밀어 올린다)
lid = D(lid, bx(-3.5, 3.5, YS-1, SWF_Y+0.25, SW_Z-3.5, SW_Z+3.5))                         # 스위치 윗부분
lid = D(lid, cyl(3.2, 10.0, (0, SWF_Y-0.3+5.0, SW_Z), axis='y'))                          # 플런저 창 Ø6.4
lid = D(lid, bx(-4.7, 4.7, YS-1, 3.2, USB_Z0+SEAT_L, TAIL_END))                           # 셸 뒤쪽 납땜 귀 · 기판 위 납땜 · 전선 여유
for z in PEG_Z:
    lid = D(lid, cyl(1.75, 4.4, (0, YS, z), axis='y', n=40))
    cs = rev([[0, -0.1], [1.75+0.6, -0.1], [1.75, 0.5], [0, 0.5]], 40)                   # 입구 모따기
    cs.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0])); cs.apply_translation([0, YS, z])
    lid = D(lid, cs)
lid = chamfer_end(lid, CR_BOT, CH_BOT, CR_R, up=False)
lid = chamfer_end(lid, CR_TOP, CH_TOP, CR_R, up=True)
for zc, s in ((CR_BOT, 1), (CR_TOP, -1)):
    lid = D(lid, prism_x([(zc-s*0.05, YS-0.05), (zc+s*EF, YS-0.05), (zc-s*0.05, YS+EF)], -8, 8))
lid = save(lid, "07b_lid_RED")

# ═══════════════════ 07c 조임 링 ═══════════════════
zb, zt = RING_ZB, RING_ZB + RING_H
ring = tube_rev([[RING_IN, zb], [RING_RR, zb], [RING_RR, zt], [RING_ID, zt], [RING_ID, zb+(RING_IN-RING_ID)]])
ridge = helix([[RING_RR-0.05, -(TH_CW/2+TH_D+0.05)], [RING_RC, -TH_CW/2], [RING_RC, TH_CW/2], [RING_RR-0.05, TH_CW/2+TH_D+0.05]],
              zb, zt)
ring = U(ring, ridge)
ring = I(ring, rev([[0, zb], [RING_RR-0.15, zb], [RING_RC+0.2, zb+TH_D+0.35], [RING_RC+0.2, zt-TH_D-0.35],
                    [RING_RR-0.15, zt], [0, zt]]))                                        # 위아래를 자르고 산 끝을 45도로
for k in range(4):                                                                        # 돌리는 홈 4개
    ring = D(ring, rotz(bx(-1.2, 1.2, RING_ID-0.6, 7.0, zt-1.4, zt+1), 90*k))
ring = save(ring, "07c_ring_RED")

# ═══════════════════ 16 링 돌리개 (공구 · 1개만) ═══════════════════
KEY_R0, KEY_R1 = 5.85, 6.95
kz0, kz1 = zt, 9.0
key = tube_rev([[KEY_R0, kz0], [KEY_R1, kz0], [KEY_R1, kz1], [11.0, kz1], [11.0, kz1+4.0], [KEY_R0, kz1+4.0]])
for k in range(12):                                                                       # 손잡이 톱니
    a = 2*math.pi*k/12; key = D(key, cyl(1.6, 6.0, (11.9*math.cos(a), 11.9*math.sin(a), kz1+2.0)))
key = D(key, bx(0, 20, -3.4, 3.4, kz0-3, kz1+5))                                          # 전선이 빠지는 옆 트임
for sg in (1, -1):                                                                        # 링 홈에 들어가는 발 2개
    key = U(key, bx(-0.95, 0.95, min(sg*KEY_R0, sg*KEY_R1), max(sg*KEY_R0, sg*KEY_R1), kz0-1.2, kz0+0.5))
key = save(key, "16_key_RED")

# ═══════════════════ 17 시험 조각 (손잡이 윗부분만 · 15분) ═══════════════════
# 손잡이 전체를 뽑기 전에 : 링이 돌아 들어가는지 · 캐리어 끝이 D자 구멍에 들어가는지 먼저 본다
test = I(hand_solid, cyl(12.0, PLUG_TOP+0.1-(FUN_Z0-3.0), (0, 0, (PLUG_TOP+0.1+FUN_Z0-3.0)/2)))
test = save(test, "17_test_RED")

# ═══════════════════ 검증 ═══════════════════
print("\n── 검증 1 : 제자리에서 안 겹친다 (0 이어야 한다) ──")
def V(a, b):
    try: return abs(vz(a.intersection(b)).volume)
    except Exception: return float('nan')
def mv(m, d): m = m.copy(); m.apply_translation(d); return m
carrier = [tray, lid]
def VC(m): return sum(V(m, c) for c in carrier)
shell = ext(stad(SK_SW, SK_SH, SK_SH/2-0.02), USB_Z0, USB_Z0+SK_SL); shell.apply_translation([0, MOUTH_Y, 0])   # 셸 (양옆이 둥글다)
pcbA  = bx(-SK_PW/2, SK_PW/2, MOUTH_Y-SK_PT/2, MOUTH_Y+SK_PT/2, USB_Z0+SK_SL-1.0, USB_Z0+SK_PL)        # 기판 (셸 가운데에 꽂힘)
pcb_v = [mv_ for mv_ in (bx(-SK_PW/2, SK_PW/2, MOUTH_Y-SK_PT/2+d, MOUTH_Y+SK_PT/2+d, USB_Z0+SK_SL-1.0, USB_Z0+SK_PL) for d in (-0.35, 0.35))]   # 기판이 가운데서 0.35 벗어나도
tabs  = [bx(-4.0, 4.0, MOUTH_Y+sg*SK_SH/2-(0.6 if sg < 0 else 0), MOUTH_Y+sg*SK_SH/2+(0.6 if sg > 0 else 0), USB_Z0+SEAT_L+0.3, USB_Z0+SK_SL) for sg in (1, -1)]   # 셸 뒤쪽 위·아래 납땜 귀 0.6
sold  = [bx(-4.0, 4.0, MOUTH_Y+SK_PT/2, MOUTH_Y+SK_PT/2+0.9, USB_Z0+SK_SL+0.2, USB_Z0+SK_PL),        # 기판 위 핀·저항·전선 납땜
         bx(-4.0, 4.0, MOUTH_Y-SK_PT/2-0.9, MOUTH_Y-SK_PT/2, USB_Z0+SK_SL+0.2, USB_Z0+SK_PL)]        # 기판 밑 납땜
sw_body = bx(-3, 3, SW_SEAT, SWF_Y, SW_Z-3, SW_Z+3)
sw_stem = cyl(1.75, SW_STEM_H, (0, SWF_Y+SW_STEM_H/2, SW_Z), axis='y')
sw_legs = [bx(sx*3.0 if sx > 0 else -3.95, 3.95 if sx > 0 else -3.0, SW_SEAT-3.5, SW_SEAT+0.5, SW_Z+sz*2.25-0.35, SW_Z+sz*2.25+0.35)
           for sx in (1, -1) for sz in (1, -1)]
swd = [sw_body, sw_stem] + sw_legs
wires = [bx(-2.0, 2.0, YB+0.1, YB+1.8, TAIL_END-3.0, CR_TOP+6),                # 등 홈을 타고 올라가는 전선 다발
         bx(-2.6, 2.6, YB+0.1, REL_Y+1.5, TAIL_END-3.2, TAIL_END-0.3),
         bx(-3.5, 3.5, STOP_Y+0.05, STOP_Y+1.1, USB_Z0+SK_PL-1.0, TAIL_END-0.5)]      # 패드 → 뒷벽 위 → 전선 칸      # 꼬리칸 → 등으로 내려가는 구멍
PLUG_LEFT = 1.91                                                    # 끝까지 꽂았을 때 남는 금속 길이 (실측)
PLUG_IN   = 6.65 - PLUG_LEFT                                        # 셸 안으로 들어가야 하는 깊이
plugm = ext(stad(PLUG_W, PLUG_H, PLUG_H/2-0.02), USB_Z0-PLUG_LEFT, USB_Z0+PLUG_IN); plugm.apply_translation([0, MOUTH_Y, 0])   # 끝까지 꽂힌 금속부
plugo = ext(stad(14.0, 8.0, 3.0), USB_Z0-PLUG_LEFT-6, USB_Z0-PLUG_LEFT); plugo.apply_translation([0, MOUTH_Y, 0])            # 몰딩 (아주 큰 것 14 x 8)
rest = mv(btn, [0, STEM_TOP-Y_TIP, 0])                                          # 버튼이 스템 위에 얹힌 위치
bad = 0
def chk(name, v, want_zero=True, note=""):
    global bad
    ok = (v < 0.05) if want_zero else (v > 0.05)
    bad += (not ok)
    print(f"  {name:34s} {v:8.3f} mm3   {'✔' if ok else '✘'}  {note}")
chk("트레이 ∩ 뚜껑", V(tray, lid))
chk("손잡이 ∩ 캐리어", VC(hand_solid))
chk("손잡이 ∩ 링", V(hand_solid, ring))
chk("링 ∩ 캐리어", VC(ring))
chk("손잡이 ∩ 갇힌버튼", V(hand_solid, btn))
chk("USB 셸 ∩ 캐리어", VC(shell))
chk("USB 기판 ∩ 캐리어", VC(pcbA))
chk("  〃 기판이 위아래 0.35 벗어나도", sum(VC(p) for p in pcb_v))
chk("셸 뒤쪽 납땜 귀(위·아래 0.6) ∩ 캐리어", sum(VC(t) for t in tabs))
chk("기판 위·아래 납땜 ∩ 캐리어", sum(VC(t) for t in sold))
chk("스위치 ∩ 캐리어", sum(VC(s) for s in swd))
chk("버튼(스템 위) ∩ 캐리어·스위치몸통", VC(rest) + V(rest, sw_body))
chk("전선 다발 ∩ 캐리어·손잡이·링", sum(VC(w)+V(w, hand_solid)+V(w, ring) for w in wires))
chk("끝까지 꽂힌 케이블(몰딩 14x8) ∩ 손잡이", V(plugm, hand_solid) + V(plugo, hand_solid))
chk("셸 ∩ 손잡이 (바닥 주머니 안)", V(shell, hand_solid))
chk("돌리개 ∩ 손잡이·링", V(key, hand_solid) + V(key, ring) - 0.0)

print("\n── 검증 2 : 걸려야 할 곳이 실제로 걸린다 (0 보다 커야 한다) ──")
chk("케이블 뽑기 → 셸이 바닥벽에", V(mv(shell, [0, 0, -0.5]), hand_solid), False)
chk("케이블 꽂기 → 기판 뒤끝이 벽에", VC(mv(pcbA, [0, 0, 0.3+0.4])), False)
chk("캐리어 위로 → 링에", VC(mv(ring, [0, 0, -0.4])), False)
chk("링 위로(안 돌리고) → 나사에", V(mv(ring, [0, 0, 0.8]), hand_solid), False)
chk("캐리어 아래로 → 바닥 원뿔에", sum(V(mv(c, [0, 0, -0.3]), hand_solid) for c in carrier), False)
chk("캐리어 옆으로 0.3 → 바닥 원뿔에", sum(V(mv(c, [0.3, 0, 0]), hand_solid) for c in carrier), False)
chk("셸 옆으로 0.3 → 옆벽에", VC(mv(shell, [0.3, 0, 0])), False)
chk("캐리어가 0.35 치우쳐 내려와도 셸이 주머니에", max(V(mv(shell, [dx, dy, d]), hand_solid) for dx, dy in ((0.35, 0), (0, 0.35), (-0.25, -0.25)) for d in (1.15, 0.9, 0.6)))
chk("셸 아래로 0.3 → 바닥에", VC(mv(shell, [0, -0.3, 0])), False)
chk("셸 위로 0.3 → 뚜껑에", V(mv(shell, [0, 0.3, 0]), lid), False)
chk("스위치 위로 0.4 → 뚜껑에", V(mv(sw_body, [0, 0.4, 0]), lid), False)
chk("스위치 아래로 → 레일에", V(mv(sw_body, [0, -0.3, 0]), tray), False)
chk("버튼 누름 0.2 → 스템에", V(mv(rest, [0, -0.2, 0]), sw_stem), False)
chk("버튼 밖으로 0.6 → 베젤에", V(mv(btn, [0, BTN_GAP+0.1, 0]), hand_solid), False)
chk("캐리어 뒤집어 넣기 → 못 들어감", sum(V(mv(rotz(c, 180), [0, 0, 2.0]), hand_solid) for c in carrier), False)

print("\n── 검증 3 : 거기까지 갈 수 있다 ──")
worst = 0; core = trimesh.util.concatenate([tray, lid, shell, pcbA] + swd)
out = mv(btn, [0, BTN_GAP-0.02, 0])                                 # 플런저가 끝까지 밀려 나간 위치
for dz in np.arange(0.3, 72, 2.0):
    c = mv(core, [0, 0, dz]); worst = max(worst, V(hand_solid, c), V(out, c))
chk("캐리어 넣는 길 (36개 위치)", worst)
# 플런저가 안쪽으로 처져 있어도 입구 경사가 밀어 올리나 : 경사 시작 높이 < 처진 플런저 끝
print(f"  플런저가 끝까지 처지면 y{Y_TIP-BTN_TRAV:.2f} · 뚜껑 입구 경사는 y3.35 부터 → "
      f"{'✔ 경사가 받는다' if Y_TIP-BTN_TRAV > 3.6 else '✘'}")
print(f"  스위치 앞 길 바닥 y{CHAN_HI} > 스템 끝 y{STEM_TOP:.2f} > 평소 길 y{CHAN_Y} → 플런저가 스템 옆구리에 안 걸린다")
worst = 0
for t in np.arange(0.25, 3.01, 0.25):                               # 링을 돌려 넣기 (돌린 만큼 내려간다)
    r_ = mv(rotz(ring, 360*t), [0, 0, TH_P*t]); worst = max(worst, V(r_, hand_solid))
chk("링 돌려 넣는 길 (12개 위치)", worst)

chk("링 그냥 밀어 넣기 → 안 들어감", V(mv(ring, [0, 0, TH_P*0.5]), hand_solid), False)
print("\n── 숫자 ──")
_f0, _f1 = HAND_BOT+LIP_T, USB_Z0+(STOP_Z-USB_Z0-SK_PL)             # 셸 앞끝이 있을 수 있는 범위
print(f"  케이블        : 끝까지 꽂히려면 손잡이 밑면~셸 앞끝 < {PLUG_LEFT} · 지금 {_f0-HAND_BOT:.2f}~{_f1-HAND_BOT:.2f} → 여유 {PLUG_LEFT-(_f1-HAND_BOT):.2f} (이전 판 : 2.0 → 모자람)")
print(f"  USB 걸림      : 뽑을 때 셸이 바닥 구멍에 편측 {(SK_SW-PLUG_W-0.16)/2:.3f} · 꽂을 때 기판 뒤끝이 벽에 (기판 두께 중 {min(STOP_Y, MOUTH_Y+SK_PT/2)-(MOUTH_Y-SK_PT/2):.2f} 물림)")
print(f"  USB 유격      : 좌우 편측 {SHL_HW-SK_SW/2:.2f} · 상하 {SEAT_Y-(MOUTH_Y-SK_SH/2):+.2f} / {YS-(MOUTH_Y+SK_SH/2):+.2f} · 앞뒤 {STOP_Z-USB_Z0-SK_PL:.2f}")
print(f"  USB 자리      : 셸을 무는 길이 {SEAT_L} · 그 뒤 여유 아래 {SEAT_Y-REL_Y:.2f} / 위 {3.2-YS:.2f} · 기판 밑 빈 공간 {MOUTH_Y-SK_PT/2-REL_Y:.2f}")
print(f"  나사          : 피치 {TH_P} · 물림 {TH_D-TH_CLR:.2f} · 틈 {TH_CLR} · 링이 물리는 바퀴 {RING_H/TH_P:.2f} · "
      f"링이 더 내려갈 수 있는 여유 {zb-TH_Z0:.2f}")
print(f"  버튼          : 평소 틈 {Y_TIP+BTN_GAP-STEM_TOP:.2f} · 누를 수 있는 깊이 {STEM_TOP-(Y_TIP-BTN_TRAV):.2f} (스위치 행정 0.25)")
print(f"  결과          : {'전부 통과' if bad == 0 else str(bad)+' 건 실패'}")

# ═══════════════════ 출력 방향 (베드에 바로 얹는 상태) ═══════════════════
P = "/home/claude/v23_plate"; os.makedirs(P, exist_ok=True)
Ry = trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0])     # +y → +z : 평면이 바닥
Rf = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])       # 뒤집기
def plate(name, rot):
    m = trimesh.load(f"{OUT}/{name}.stl")
    if rot is not None: m.apply_transform(rot)
    b = m.bounds; m.apply_translation([-(b[0][0]+b[1][0])/2, -(b[0][1]+b[1][1])/2, -b[0][2]])
    nz = m.face_normals[:, 2]; zc = m.triangles_center[:, 2]
    ov = m.area_faces[(nz < -0.72) & (zc > 0.3)].sum()                  # 45도 넘는 아랫면 (베드 제외)
    br = m.area_faces[(nz < -0.999) & (zc > 0.3)].sum()                 # 그중 수평 천장 (브리지)
    m.export(f"{P}/{name}.stl"); e = m.bounds[1]-m.bounds[0]
    print(f"  {name:16s} {e[0]:5.1f} x {e[1]:5.1f} x {e[2]:5.1f}   서포트 필요면 {ov-br:6.1f}mm2 · 브리지 {br:6.1f}mm2")
print("\n── 출력 방향 ──")
plate("05_handle_RED", None); plate("07a_tray_RED", Ry); plate("07b_lid_RED", Ry)
plate("07c_ring_RED", Rf); plate("16_key_RED", Rf); plate("17_test_RED", None)
