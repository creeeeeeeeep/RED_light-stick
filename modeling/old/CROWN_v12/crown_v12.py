"""
CROWN MINI CHEER STICK — v11
레드 단색 왕관 + 화이트 확산 돔 · 손잡이 Ø17 · 전장 ~129mm
배선: 보드 5V/GND/GPIO19/20 패드 → 가는 선 4가닥 → 손잡이 끝 USB-C 암 브레이크아웃
      (커넥터가 구멍을 통과할 필요가 없어져 손잡이가 Ø19 → Ø17 로 얇아짐)
보드: Waveshare ESP32-S3-Matrix (25 x 25 x 5.5, LED 상향)

내부 적층이 밴드 높이를 결정한다:
  뚜껑 4.6 + 스프링 1.4 + 보드 5.5 + 걸림탭 1.6 + 돔립 1.9 = 15.0
"""
import numpy as np, math, os, trimesh
from shapely.geometry import Polygon as SPoly, box as sbox
from shapely.ops import unary_union
from shapely.affinity import translate as stranslate

OUT = "/home/claude/v12"; os.makedirs(OUT, exist_ok=True)
SEG = 160

# ═══════════════════ 파라미터 ═══════════════════
BOARD_W, BOARD_T = 25.0, 5.5      # 보드 (실측 후 수정)
CLR       = 0.4
LED_W     = 20.6                  # LED 매트릭스 한 변 (가정)

HEAD_R    = 23.5                  # Ø47
LID_T     = 2.6                   # 바닥 뚜껑 (케이블 통로가 없어져 얇아짐)
SPR_H     = 2.2                   # 스프링 눌린 높이 (링 0.6 + 배선 1.6 통과)
SPR_FREE  = 3.0
SPR_T     = 0.6
TAB_T     = 1.6                   # 보드 걸림탭 두께
LIP_D     = 1.9                   # 돔 립 물림 깊이
BAND_H    = LID_T + SPR_H + BOARD_T + TAB_T + LIP_D          # 15.0
LIGHT_R   = 15.5                  # 빛 구멍 (보드 반폭 12.5 < 15.5 < 모서리 17.68)

CUP_IN, CUP_T, CUP_UP = 20.6, 2.6, 20.0
NPT       = 8                     # 왕관 뿔
DOME_MAX, DOME_H, DOME_WALL = 19.6, 29.0, 1.6

HAND_R    = 8.5                   # Ø17
BORE_R    = 6.5                   # Ø13  ← 암 브레이크아웃 대각선 12.1 이 하한
HAND_TOP, HAND_BOT = -8.0, -57.5
COL_TOP_R = HEAD_R - 9.5

FB_W, FB_T, FB_L = 11.0, 5.0, 14.0           # USB-C 암 브레이크아웃 (실측 후 수정)
AP_W, AP_T = 9.6, 4.6                        # 플러그가 들어가는 구멍
WIRE_D    = 1.2                              # 배선 지름 (USB 4 + 버튼 2 = 6가닥)
WIRE_CH   = 1.3                              # 뚜껑 윗면 배선 홈 깊이

SW_Z, SW_BODY, SW_DEEP = -18.0, 6.4, 3.7     # 전송 버튼 (택트 6x6, 캡 달린 것)
PAD_UP, LIDW, LIDT = 2.2, 10.6, 1.5
BTN_POS   = [(8.0, -8.0), (-8.0, -8.0)]      # BOOT/RESET 플런저 (보드 바닥면, 실측 후)
BTN_D     = 3.2

Z0 = BAND_H                                   # 돔 밑면
Z_LID, Z_BRD, Z_BTOP = LID_T, LID_T+SPR_H, LID_T+SPR_H+BOARD_T   # 4.6 / 6.0 / 11.5
Z_TAB = Z_BTOP + TAB_T                                            # 13.1

# ═══════════════════ 헬퍼 ═══════════════════
def vz(m):
    m.merge_vertices(); m.update_faces(m.nondegenerate_faces()); m.remove_unreferenced_vertices()
    trimesh.repair.fix_inversion(m); trimesh.repair.fix_normals(m); trimesh.repair.fill_holes(m)
    if m.volume < 0: m.invert()
    return m

def bez(p, n=70):
    p = np.array(p, float); t = np.linspace(0, 1, n)[:, None]
    return ((1-t)**3)*p[0] + 3*((1-t)**2)*t*p[1] + 3*(1-t)*t**2*p[2] + t**3*p[3]

def rev(prof, seg=SEG, lo=True, hi=True):
    P = np.asarray(prof, float); th = np.linspace(0, 2*np.pi, seg, endpoint=False)
    V = [np.column_stack([r*np.cos(th), r*np.sin(th), np.full(seg, z)]) for r, z in P]
    V = np.vstack(V); K = len(P); F = []
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
    """축에 닿지 않는 닫힌 (r,z) 단면 → 튜브형 회전체"""
    L = np.asarray(loop, float)
    a = sum(L[i, 0]*L[(i+1) % len(L), 1] - L[(i+1) % len(L), 0]*L[i, 1] for i in range(len(L)))
    if a < 0: L = L[::-1]
    return rev(np.vstack([L, L[:1]]), seg, lo=False, hi=False)

def shell(prof, t):
    P = np.asarray(prof, float)
    return tube_rev(np.vstack([P, np.column_stack([P[:, 0]+t, P[:, 1]])[::-1]]))

def box(sx, sy, sz, pos=(0, 0, 0)):
    b = trimesh.creation.box((sx, sy, sz)); b.apply_translation(pos); return b

def cyl(r, h, pos=(0, 0, 0), axis='z'):
    c = trimesh.creation.cylinder(radius=r, height=h, sections=96)
    if axis == 'y': c.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]))
    if axis == 'x': c.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [0, 1, 0]))
    c.apply_translation(pos); return c

def stad(w, d, r=None):
    if r is None: r = min(w, d)/2 - 0.15
    return sbox(-w/2, -d/2, w/2, d/2).buffer(-r, resolution=24).buffer(r, resolution=24)

def scallop(th0, th1, ztop, zdip, h, r_in, r_out, p=1.8, M=26):
    s = np.linspace(0, 1, M); th = th0 + s*(th1-th0)
    zb = zdip + h*np.power(np.abs(2*s-1), p)
    V, F = [], []
    for k in range(M):
        c, sn = math.cos(th[k]), math.sin(th[k])
        for (r, z) in [(r_in, zb[k]), (r_out, zb[k]), (r_out, ztop), (r_in, ztop)]:
            V.append([r*c, r*sn, z])
    for k in range(M-1):
        a, b = 4*k, 4*(k+1)
        for q in range(4):
            q2 = (q+1) % 4
            F.append([a+q, a+q2, b+q2]); F.append([a+q, b+q2, b+q])
    F += [[0, 2, 1], [0, 3, 2]]
    a = 4*(M-1); F += [[a, a+1, a+2], [a, a+2, a+3]]
    return vz(trimesh.Trimesh(np.array(V), np.array(F), process=True))

def teardrop(r, pos):
    """구 + 아래쪽 45도 원뿔 — 서포트 없이 뽑히는 구슬"""
    s = trimesh.creation.icosphere(subdivisions=2, radius=r)
    c = rev(np.array([[0, -r*1.35], [r*0.999, 0.0], [0, 0.0]]), 48)
    m = vz(trimesh.boolean.union([vz(s), vz(c)]))
    m.apply_translation(pos); return m

def text_poly(s, size):
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    tp = TextPath((0, 0), s, size=size, prop=FontProperties(family='DejaVu Sans', weight='bold'))
    polys = sorted([SPoly(np.asarray(p)).buffer(0) for p in tp.to_polygons() if len(p) > 2],
                   key=lambda p: -p.area)
    out = polys[0]
    for p in polys[1:]:
        out = out.symmetric_difference(p) if out.contains(p) else out.union(p)
    c = out.centroid
    return stranslate(out, -c.x, -c.y)

def emboss(poly, depth, at_y, z):
    g = list(poly.geoms) if poly.geom_type == 'MultiPolygon' else [poly]
    m = trimesh.util.concatenate([trimesh.creation.extrude_polygon(x, depth) for x in g])
    m.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]))
    m.apply_scale([-1, 1, 1]); m.apply_translation([0, at_y, z])
    return vz(m)

log = []
def save(m, name, expect=1):
    m = vz(m); m.export(f"{OUT}/{name}.stl")
    e = m.bounds[1]-m.bounds[0]; nb = len(m.split(only_watertight=False))
    flag = "" if nb == expect else f"  ⚠ 덩어리 {nb}개!"
    log.append((name, m))
    print(f"  {name:22s} {e[0]:5.1f} x {e[1]:5.1f} x {e[2]:5.1f}  vol {m.volume/1000:5.2f}cm3  "
          f"wt={str(m.is_watertight):5s}{flag}")
    return m

print("CROWN MINI CHEER STICK v11\n")

# ═══════════════ 01 확산 돔 (화이트) ═══════════════
dout = bez([[18.4, Z0], [DOME_MAX+0.6, Z0+8], [17.0, Z0+22], [2.8, Z0+DOME_H]], 80)
dome = rev(np.vstack([[[0, Z0]], dout]), lo=False, hi=True)
dinn = np.column_stack([np.clip(dout[:, 0]-DOME_WALL, 0, None), dout[:, 1]])
dome = vz(dome.difference(rev(np.vstack([[[0, Z0-4]], [[dinn[0, 0], Z0-4]], dinn, [[0, dinn[-1, 1]]]]))))
# 밴드에 꽂히는 립 + 립을 셸에 잇는 웹 (웹이 없으면 립이 따로 떨어져 나온다)
lip = tube_rev([[LIGHT_R-1.6, Z0], [LIGHT_R-0.15, Z0], [LIGHT_R-0.15, Z0-LIP_D], [LIGHT_R-1.6, Z0-LIP_D]])
web = tube_rev([[LIGHT_R-1.6, Z0], [18.4-DOME_WALL+0.4, Z0], [18.4-DOME_WALL+0.4, Z0+1.0], [LIGHT_R-1.6, Z0+1.0]])
dome = vz(dome.union(lip)); dome = vz(dome.union(web))
# 정수리 : 오브 꽂이 소켓
FIN_PEG = 3.2
dome = vz(dome.difference(cyl(FIN_PEG/2+0.2, 12.0, (0, 0, Z0+DOME_H-3.0))))
save(dome, "01_dome_WHITE")

# ═══════════════ 02 왕관 + 밴드 (레드, 한 몸) ═══════════════
bprof = np.vstack([
    bez([[COL_TOP_R, -0.8], [HEAD_R-4.6, 2.6], [HEAD_R-0.3, 4.6], [HEAD_R, 6.6]], 30),
    [[HEAD_R, BAND_H-2.6]],
    bez([[HEAD_R, BAND_H-2.6], [HEAD_R, BAND_H-1.2], [HEAD_R-1.2, BAND_H-0.2], [HEAD_R-2.4, BAND_H]], 18)])
crown = rev(np.vstack([[[0, -0.8]], bprof, [[0, BAND_H]]]))
# 왕관 받침 : 밴드에서 곧게 세우고 위로 갈수록 살짝 벌어지게
cp = bez([[CUP_IN, BAND_H-1.8], [CUP_IN+0.3, BAND_H+3.0],
          [CUP_IN+0.6, BAND_H+12.0], [CUP_IN+0.9, BAND_H+CUP_UP]], 44)
crown = vz(crown.union(shell(cp, CUP_T)))
for i in range(NPT):
    a = 2*math.pi*i/NPT; w = 2*math.pi/NPT
    crown = vz(crown.difference(scallop(a-w*0.5, a+w*0.5, BAND_H+CUP_UP+16,
                                        BAND_H+5.0, CUP_UP-5.0, 4.0, HEAD_R+12)))
for i in range(NPT):                                   # 뿔 끝 구슬 (티어드롭)
    a = 2*math.pi*i/NPT + math.pi/NPT
    crown = vz(crown.union(teardrop(2.4, ((cp[-1, 0]+CUP_T*0.5)*math.cos(a),
                                          (cp[-1, 0]+CUP_T*0.5)*math.sin(a), cp[-1, 1]+0.4))))
for i in range(NPT):                                   # 마름모 문양 (아래쪽 45도 = 서포트 불필요)
    a = 2*math.pi*i/NPT + math.pi/NPT
    zc = BAND_H + 3.4
    r = np.interp(zc, cp[:, 1], cp[:, 0]) + CUP_T
    d = box(6.4, 2.0, 6.4)
    d.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4, [0, 1, 0]))
    d.apply_translation([0, r-0.5, zc])
    d.apply_transform(trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
    crown = vz(crown.union(d))
# RED 명판 (밑면 45도 챔퍼로 서포트 제거)
PLY = HEAD_R - 1.2
plate = box(19.0, 5.0, 6.4, (0, PLY, 9.0))
ch = box(30, 30, 30); ch.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4, [1, 0, 0]))
ch.apply_translation([0, PLY+2.5-21.2, 9.0-3.2-21.2])
crown = vz(crown.union(vz(plate.difference(ch))))
crown = vz(crown.union(emboss(text_poly("RED", 5.6), 1.2, PLY+2.5+1.0, 9.0)))

# ── 내부 ──
crown = vz(crown.difference(box(BOARD_W+CLR*2, BOARD_W+CLR*2, Z_BTOP*2, (0, 0, 0))))   # 보드+스프링 (아래로 열림)
crown = vz(crown.difference(cyl(LIGHT_R, 80, (0, 0, Z_BTOP+40))))                       # 빛 구멍
crown = vz(crown.difference(tube_rev([[LIGHT_R-1.65, BAND_H], [LIGHT_R-0.1, BAND_H],
                                      [LIGHT_R-0.1, BAND_H-LIP_D-0.1], [LIGHT_R-1.65, BAND_H-LIP_D-0.1]])))
# 커넥터가 헤드 안에 없다. 보드 패드에 직접 납땜한 선 6가닥만 아래로 내려간다.
seat = trimesh.creation.extrude_polygon(stad(28.6, 28.6, 6.0), LID_T)                    # 뚜껑 자리
seat.apply_translation([0, 0, 0]); crown = vz(crown.difference(seat))
for i in range(2):                                                                       # 스냅 후크가 걸리는 홈 (뚜껑 자리 벽)
    sl = box(7.0, 1.6, 1.3, (0, 14.3, 3.1))
    sl.apply_transform(trimesh.transformations.rotation_matrix(math.pi*i, [0, 0, 1]))
    crown = vz(crown.difference(sl))
save(crown, "02_crown_RED")

# ═══════════════ 03 바닥 뚜껑 (레드) ═══════════════
lid = trimesh.creation.extrude_polygon(stad(28.3, 28.3, 6.0), LID_T)
lid = vz(lid.difference(cyl(BORE_R-0.3, LID_T*4, (0, 0, LID_T/2))))                      # 배선 관통
so = trimesh.creation.extrude_polygon(stad((HAND_R+0.3)*2, (HAND_R+0.3)*2), 2.0)          # 손잡이 스피곳 자리
so = vz(so.difference(cyl(BORE_R-0.3, 8.0, (0, 0, 1.0))))
lid = vz(lid.difference(so))
# 윗면 배선 홈 : 보드 패드가 어디든 선을 중앙 구멍까지 끌어올 수 있게 원형 + 방사형
lid = vz(lid.difference(cyl(10.6, WIRE_CH*2, (0, 0, LID_T))))
for i in range(4):
    g = box(25.6, WIRE_D*2.4, WIRE_CH*2, (0, 0, LID_T))
    g.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4*i, [0, 0, 1]))
    lid = vz(lid.difference(g))
plungers = []
SH_TOP = Z_BRD - 0.95
for (bx, by) in BTN_POS:
    lid = vz(lid.difference(cyl(BTN_D/2, LID_T*4, (bx, by, LID_T/2))))
    pass
# 스냅 후크 : 뚜껑 가장자리를 ㄷ자로 따내 외팔보를 만들고 바깥으로 걸림턱
for i in range(2):
    T = trimesh.transformations.rotation_matrix(math.pi*i, [0, 0, 1])
    for sx in (-1, 1):                                       # 양옆 세로 슬릿
        sl = box(1.0, 4.2, LID_T, (sx*3.6, 12.6, 0.8+LID_T/2)); sl.apply_transform(T)
        lid = vz(lid.difference(sl))
    sl = box(8.2, 1.0, LID_T, (0, 10.9, 0.8+LID_T/2)); sl.apply_transform(T)   # 안쪽 가로 슬릿
    lid = vz(lid.difference(sl))
    barb = box(6.2, 1.1, 1.2, (0, 14.15, 3.1)); barb.apply_transform(T)        # 걸림턱 0.5 돌출
    lid = vz(lid.union(barb))
save(lid, "03_lid_RED")
print(f"  {'(BOOT/RESET)':22s} 뚜껑에 Ø{BTN_D} 접근 구멍만. 손잡이를 빼고 이쑤시개로 누른다")

# ═══════════════ 04 보드 밀어올림 스프링 (레드) ═══════════════
SPR_W, SPR_IN, LEAF_L, LEAF_W = 24.8, 22.0, 7.0, 4.0
ring = box(SPR_W, SPR_W, SPR_T, (0, 0, SPR_T/2))
ring = vz(ring.difference(box(SPR_IN, SPR_IN, SPR_T*4, (0, 0, SPR_T/2))))
leaves = [ring]
for i in range(4):
    r0, r1, rise = SPR_IN/2, SPR_IN/2-LEAF_L, SPR_FREE-SPR_T
    V = np.array([[r0,-LEAF_W/2,0],[r0,LEAF_W/2,0],[r1,-LEAF_W/2,rise],[r1,LEAF_W/2,rise],
                  [r0,-LEAF_W/2,SPR_T],[r0,LEAF_W/2,SPR_T],[r1,-LEAF_W/2,rise+SPR_T],[r1,LEAF_W/2,rise+SPR_T]], float)
    F = np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,2,6],[0,6,4],[1,5,7],[1,7,3],[0,4,5],[0,5,1],[2,3,7],[2,7,6]])
    lf = vz(trimesh.Trimesh(V, F, process=True))
    lf.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2*i, [0, 0, 1]))
    leaves.append(lf)
spring = vz(trimesh.boolean.union([vz(x) for x in leaves]))
# 링을 자르지 않는다. 선은 링 위 1.6mm 틈으로 지나간다 (SPR_H 2.2 - 링 0.6)
spring.apply_translation([0, 0, Z_LID])
save(spring, "04_spring_RED")

# ═══════════════ 05 손잡이 + 칼라 (레드) ═══════════════
hp = np.vstack([[[HAND_R, HAND_BOT]],
      bez([[HAND_R, HAND_TOP-4.0], [HAND_R+0.4, HAND_TOP-1.0], [HAND_R+2.6, HAND_TOP+1.6],
           [COL_TOP_R, -0.8]], 34)])
hand = rev(np.vstack([[[0, HAND_BOT]], hp, [[0, -0.8]]]))
hand = vz(hand.union(rev(np.array([[0, -0.8], [HAND_R+0.3, -0.8], [HAND_R+0.3, 1.7], [0, 1.7]]))))  # 스피곳
hand = vz(hand.difference(cyl(BORE_R, 200, (0, 0, HAND_BOT-40))))                                   # 구멍
for i in range(12):                                                                                 # 세로 홈
    a = 2*math.pi*i/12
    hand = vz(hand.difference(cyl(0.8, abs(HAND_TOP-HAND_BOT)*0.58,
                                  ((HAND_R+0.3)*math.cos(a), (HAND_R+0.3)*math.sin(a), (HAND_TOP+HAND_BOT)/2-3))))
dia = box(8.4, 2.4, 8.4)                                                                            # 마름모 엠블럼
dia.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4, [0, 1, 0]))
dia.apply_translation([0, HAND_R-0.6, HAND_TOP-4.5])
hand = vz(hand.union(dia))
# 전송 버튼 자리
YF = HAND_R
pad = trimesh.creation.extrude_polygon(stad(13.0, 12.0, 3.0), PAD_UP+2.0)
pad.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
pad.apply_translation([0, YF-2.0, SW_Z]); hand = vz(hand.union(pad))
SW_BACK = YF + PAD_UP - LIDT - SW_DEEP
ib = box(SW_BODY+3.0, YF-SW_BACK, SW_BODY+3.0, (0, (YF+SW_BACK)/2, SW_Z))
chm = box(24, 24, 24); chm.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4, [1, 0, 0]))
chm.apply_translation([0, SW_BACK-8.49, SW_Z-(SW_BODY+3.0)/2-8.49])
hand = vz(hand.union(vz(ib.difference(chm))))
rc = trimesh.creation.extrude_polygon(stad(LIDW, LIDW, 2.0), LIDT+2.0)
rc.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
rc.apply_translation([0, YF+PAD_UP-LIDT, SW_Z]); hand = vz(hand.difference(rc))
hand = vz(hand.difference(box(SW_BODY, SW_DEEP+2.0, SW_BODY, (0, YF+PAD_UP-LIDT-(SW_DEEP+2.0)/2+1.0, SW_Z))))
for sg in (1, -1):
    hand = vz(hand.difference(box(1.4, 1.0, 3.8, (sg*LIDW/2, YF+PAD_UP-0.75, SW_Z))))
# 발 + 스트랩 탭
foot = rev(np.array([[0, HAND_BOT-5.5], [5.6, HAND_BOT-5.5], [HAND_R, HAND_BOT-0.4], [HAND_R, HAND_BOT], [0, HAND_BOT]]))
hand = vz(hand.union(foot))
# 암 브레이크아웃이 앉는 자리 + 플러그가 들어가는 구멍
bay = trimesh.creation.extrude_polygon(stad(FB_W+0.5, FB_T+0.5, 1.0), FB_L+2.0)
bay.apply_translation([0, 0, HAND_BOT-1.6])
hand = vz(hand.difference(bay))
ap = trimesh.creation.extrude_polygon(stad(AP_W, AP_T, 1.6), 8.0)
ap.apply_translation([0, 0, HAND_BOT-7.0])
hand = vz(hand.difference(ap))
# 스트랩 귀 : USB 구멍을 피해 옆으로 뻗는다
EAR_T, EAR_L = 4.2, 8.0
e2d = sbox(-3.6, -(HAND_R+EAR_L), 3.6, -HAND_R+3.0).buffer(-3.0, resolution=20).buffer(3.0, resolution=20)
ear = trimesh.creation.extrude_polygon(e2d, EAR_T)
ear.apply_translation([0, 0, HAND_BOT-5.5])
ear = vz(ear.difference(cyl(2.5, 12, (0, -(HAND_R+EAR_L-3.4), HAND_BOT-5.5+EAR_T/2))))
hand = vz(hand.union(ear))
BOSS = float(np.round((YF-2.0)-SW_BACK, 2))
print(f"  [버튼] 보스가 구멍을 {(YF-2.0)-SW_BACK:.2f}mm 먹음 (구멍 반지름 {BORE_R})")
save(hand, "05_handle_RED")

# ═══════════════ 06 버튼 뚜껑 (레드) ═══════════════
bl = trimesh.creation.extrude_polygon(stad(LIDW-0.3, LIDW-0.3, 2.0), LIDT-0.2)
bl = vz(bl.difference(cyl(2.9, LIDT*4, (0, 0, 0))))
bl = vz(bl.union(tube_rev([[3.2, 0.0], [4.4, 0.0], [4.4, -0.8], [3.2, -0.8]])))
for sg in (1, -1):
    bl = vz(bl.union(box(1.0, 3.6, 0.7, (sg*(LIDW-0.3)/2, 0, LIDT-0.55))))
save(bl, "06_btncap_RED")

# ═══════════════ 08 오브(피니얼) + 09 십자가 (레드) ═══════════════
ORB_R = 4.8
Z_APEX = Z0 + DOME_H
ORB_Z = Z_APEX + 2.2 + ORB_R
fin = rev(np.array([[0, Z_APEX-2.6], [4.4, Z_APEX-1.0], [3.0, Z_APEX+3.0], [1.8, ORB_Z], [0, ORB_Z]]))
fin = vz(fin.union(trimesh.creation.icosphere(subdivisions=3, radius=ORB_R).apply_translation([0, 0, ORB_Z]) or
                   trimesh.creation.icosphere(subdivisions=3, radius=ORB_R)))
orb = trimesh.creation.icosphere(subdivisions=3, radius=ORB_R); orb.apply_translation([0, 0, ORB_Z])
fin = vz(trimesh.boolean.union([vz(fin), vz(orb)]))
fin = vz(fin.union(cyl(FIN_PEG/2, 6.0, (0, 0, Z_APEX-2.6-2.4))))                 # 돔에 꽂는 다리
_g = np.column_stack([dout[:, 0]+0.3, dout[:, 1]])                               # 돔을 0.3 부풀려
fin = vz(fin.difference(rev(np.vstack([[[0, Z0-2]], [[_g[0, 0], Z0-2]], _g, [[0, _g[-1, 1]]]]))))
CR = dict(t=3.6, a=2.2, b=2.8, lx=6.5, up=8.5, dn=5.0, peg=6.0, fil=0.9)
CROSS_Z = ORB_Z + ORB_R - 1.0
fin = vz(fin.difference(box(CR['a']*2+0.4, CR['t']+0.4, CR['peg']+6.0, (0, 0, CROSS_Z-CR['peg']/2+2.0))))
save(fin, "08_finial_RED")

arms = []
for dx, dy, L in [(1,0,CR['lx']), (-1,0,CR['lx']), (0,1,CR['up']), (0,-1,CR['dn'])]:
    px, py = -dy, dx
    arms.append(SPoly([(px*CR['a'], py*CR['a']), (dx*L+px*CR['b'], dy*L+py*CR['b']),
                       (dx*L-px*CR['b'], dy*L-py*CR['b']), (-px*CR['a'], -py*CR['a'])]))
cpo = unary_union(arms).buffer(CR['fil'], resolution=16).buffer(-CR['fil'], resolution=16)
cpo = cpo.buffer(0.5, resolution=16).buffer(-0.5, resolution=16)
cpo = cpo.union(sbox(-CR['a'], -CR['dn']-CR['peg'], CR['a'], -CR['dn']+1.0))
cross_flat = trimesh.creation.extrude_polygon(cpo, CR['t']); cross_flat.apply_translation([0, 0, -CR['t']/2])
save(cross_flat, "09_cross_RED")
cross = cross_flat.copy()
cross.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]))
cross.apply_translation([0, 0, CROSS_Z + CR['dn']]); cross = vz(cross)
cross.export(f"{OUT}/_cross_placed.stl")

TOTAL = (CROSS_Z + CR['dn'] + CR['up']) - (HAND_BOT-5.5)
print(f"\n  전장 {TOTAL:.1f}mm · 헤드 Ø{HEAD_R*2:.0f} · 손잡이 Ø{HAND_R*2:.0f}(구멍 Ø{BORE_R*2:.0f}) · 밴드 {BAND_H:.1f}mm")
