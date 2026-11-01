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
from shapely.geometry import Polygon as SPoly, box as sbox, Point as SPt
from shapely.ops import unary_union
from shapely.affinity import translate as stranslate

OUT = "/home/claude/v18"; os.makedirs(OUT, exist_ok=True)
SEG = 160

# ═══════════════════ 파라미터 ═══════════════════
BOARD_W, BOARD_T = 25.0, 5.5      # 보드 (실측 후 수정)
LED_W     = 20.6                  # LED 매트릭스 한 변 (가정)

# ═══ 공차 (v14 에서 안 들어간다는 피드백 반영) ═══
#  FDM 은 구멍이 작게, 돌기가 크게 나온다. 각각 0.1~0.2 씩이라 합쳐서 0.2~0.4 가 먹힌다.
#  그래서 도면상 0.15 는 실제로 마이너스가 된다.
FIT_SLIDE = 0.35                  # 손으로 넣고 뺄 수 있어야 하는 곳
FIT_BOARD = 0.60                  # 보드 : 25mm 큰 면이라 수축이 누적된다
FIT_PRESS = 0.25                  # 작은 꽂이 (꽉 물려 안 빠져야)
CHAM      = 0.6                   # 입구 모따기 (넣을 때 스스로 안내되게)
LID_HW    = 14.15                 # 뚜껑 반폭
SEAT_HW   = LID_HW + FIT_SLIDE    # 왕관 쪽 자리 반폭
BARB_OUT  = 1.0                   # 스냅 걸림턱 돌출 (공차만큼 먹히므로 0.55 → 1.0)

HEAD_R    = 23.5                  # Ø47
LID_T     = 2.6                   # 바닥 뚜껑 (케이블 통로가 없어져 얇아짐)
# ═══ 보드 밀어올림 스프링 (v18 : 완전 평판 스파이럴) ═══
#  v17 은 19도 램프라 서포트가 반드시 붙었고, 0.6mm 잎이라 힘도 5N 뿐이었다.
#  평판으로 바꾸면 서포트가 0 이고, 두께를 3배로 올려도 출력이 더 쉬워진다.
SPR_H     = 3.2                   # 뚜껑 윗면 ~ 보드 밑면 (배선 1.4 통과 여유 포함)
SPR_T     = 1.8                   # 판 두께 (전부 평평)
SPR_OUT   = 24.8                  # 바깥
SPR_RIMIN = 10.6                  # 테두리 안쪽 = 뚜껑 릴리프(Ø21.2) 경계
ARM_W     = 2.6                   # 팔 폭
ARM_R0, ARM_R1 = 10.9, 8.2        # 팔 시작/끝 반지름
ARM_SWEEP = 75.0                  # 팔이 도는 각도 — 힘을 여기로 조절한다
BOSS_R, BOSS_H = 1.6, 2.1         # 보드를 미는 기둥 (수직 원통 = 서포트 없음)
PAD_R     = BOSS_R + 0.5          # 기둥이 앉는 팔 끝 패드 — 기둥보다 커야 뜬 면이 안 생긴다
SPR_PUSH  = SPR_T + BOSS_H - SPR_H  # 눌리는 양 0.7
TAB_T     = 1.6                   # 보드 걸림탭 두께
LIP_D     = 1.9                   # 돔 립 물림 깊이
BAND_H    = LID_T + SPR_H + BOARD_T + TAB_T + LIP_D          # 15.0
LIGHT_R   = 15.5                  # 빛 구멍 (보드 반폭 12.5 < 15.5 < 모서리 17.68)

CUP_IN, CUP_T, CUP_UP = 20.6, 2.6, 20.0
BEAD_R    = 2.7                   # 뿔 끝 구슬
BLADE_L   = 10.0                  # 뿔 첨탑 보강 길이
BLADE_WT  = 1.75                  # 첨탑 접선 반폭 (끝)  — v13 실루엣 유지
BLADE_WB  = 3.55                  # 첨탑 접선 반폭 (뿌리)
BLADE_T   = 4.10                  # 첨탑 반경 두께 (끝). 벽은 2.6
NPT       = 8                     # 왕관 뿔
DOME_MAX, DOME_H, DOME_WALL = 19.6, 29.0, 1.6
# 돔 꼭대기 = 피니얼이 앉는 평평한 자리 + 위로 솟은 D컷 축 (자리잡기 키)
DOME_SEAT_R = 4.4                 # 자리 반지름 (피니얼 밑면과 같게 → 단이 안 생긴다)
DOME_SOLID  = 2.0                 # 자리 밑 통짜 두께
PEG_R, PEG_H, PEG_FLAT = 2.40, 3.4, 1.60      # 축 반지름 / 높이 / D컷 평면 위치
KEY_W       = 3.4                 # 돔↔왕관 방향키 폭

HAND_R    = 8.5                   # Ø17
BORE_R    = 7.0                   # Ø14 — 벽 1.5. 캐리어에 스위치를 태우려면 이만큼 필요하다
HAND_TOP, HAND_BOT = -12.0, -63.0            # 칼라를 길게 빼서 45도 이하로             # 손잡이가 바닥까지 (엔드캡 없음)
BOT_WALL  = 1.4                   # 손잡이 바닥 벽 (플러그 구멍이 뚫린다)
BOT_SINK  = 1.4                   # 플러그 오버몰드가 잠기는 자리
SKIRT_R   = 19.5                  # 왕관 밑 스커트 Ø39 — 보드 대각(17.68)+뚜껑을 감싸려면 이만큼 필요
SKIRT_TOP = 3.4                   # 스커트가 직선인 구간
POK_CR    = 1.2                   # 보드 자리 모서리 라운드 (보드 R 만큼만)
LID_CR    = 8.0                   # 뚜껑/자리 모서리 라운드 — 최대반지름을 낮춰 스커트 안에 넣는다
COL_TOP_R = SKIRT_R

# ═══ USB-C 암 브레이크아웃 (6패드형, CC1/CC2 나온 것) ═══
#  ★★ 아래 5개는 실물 캘리퍼로 재서 고칠 것. 전부 가정값이다 ★★
SK_SW, SK_SH = 8.94, 3.26        # 리셉터클 금속 셸 (USB-C 표준값)
SK_SL        = 7.40              # 셸 앞면~뒷면 길이
SK_PW, SK_PT = 9.60, 1.00        # 브레이크아웃 PCB 폭 / 두께
SK_PL        = 12.50             # PCB 전체 길이 (셸 앞면 기준)
PLUG_W, PLUG_H = 8.34, 2.56      # 수 플러그가 들어가는 부분 (USB-C 표준값)
KEY_RW, KEY_RD = 2.2, 0.4        # 캐리어 방향키 리브 폭 / 구멍 벽으로 들어가는 깊이
WIRE_D    = 1.2                              # 배선 지름 (USB 4 + 버튼 2 = 6가닥)
WIRE_CH   = 1.3                              # 뚜껑 윗면 배선 홈 깊이

# ═══ 전송 버튼 : 택트 스위치 (옴론 B3F 계열, 다리 4개) ★ 실측할 것 ★ ═══
SW_Z     = -22.0                  # 스위치 중심 높이 (칼라를 피해 내려감)
SW_W     = 6.0                    # 몸통 한 변
SW_DEEP  = 3.7                    # 몸통 높이 (누르는 방향)
SW_LEGS  = 6.5                    # 마주보는 다리 끝 사이 — 몸통(6.0)보다 넓다.
                                  #   v15 는 자리를 6.4 로 파놔서 다리가 벽에 걸려 휘었다
SW_LEGL  = 1.4                    # 다리가 몸통 뒤로 나온 길이 (1.2mm 로 잘라 쓸 것)
SW_FLOOR = 1.4                    # 다리 슬롯 밑 바닥 기둥 두께
PAD_UP, LIDW, LIDT = 2.5, 10.6, 1.6
BTN_HOLE, BTN_BOSS = 6.0, 5.6     # 벽 관통구 / 버튼 플런저 지름
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

def loft_rings(rings):
    N = len(rings[0]); K = len(rings)
    V = [v for R in rings for v in R.tolist()]; F = []
    for k in range(K-1):
        for i in range(N):
            j = (i+1) % N
            F.append([k*N+i, k*N+j, (k+1)*N+j]); F.append([k*N+i, (k+1)*N+j, (k+1)*N+i])
    c0 = len(V); V.append(np.mean(rings[0], axis=0).tolist())
    for i in range(N): F.append([c0, (i+1) % N, i])
    c1 = len(V); V.append(np.mean(rings[-1], axis=0).tolist()); b = (K-1)*N
    for i in range(N): F.append([c1, b+i, b+(i+1) % N])
    return vz(trimesh.Trimesh(np.array(V), np.array(F), process=True))

def rect_ring(hx, hy, n=48):
    """모서리를 항상 같은 인덱스에 두어야 두 링을 이어도 안 꼬인다"""
    m = n//4; t = np.linspace(0, 1, m, endpoint=False); P = []
    P += [[-hx+2*hx*u, -hy] for u in t]; P += [[hx, -hy+2*hy*u] for u in t]
    P += [[hx-2*hx*u, hy] for u in t];   P += [[-hx, hy-2*hy*u] for u in t]
    return np.array(P)

def sq_ring(h, n=48):
    return rect_ring(h, h, n)

def frustum(h0, h1, z0, z1, n=48):
    """정사각 단면 사다리꼴 — 포켓 입구 모따기용"""
    return loft_rings([np.column_stack([sq_ring(h0, n), np.full(n, z0)]),
                       np.column_stack([sq_ring(h1, n), np.full(n, z1)])])

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
SEAT_Z = Z0 + DOME_H - 2.6                                  # 피니얼이 앉는 평면
dout = bez([[18.4, Z0], [DOME_MAX+0.6, Z0+8], [17.0, Z0+22], [DOME_SEAT_R, SEAT_Z]], 80)
dome = rev(np.vstack([[[0, Z0]], dout]), lo=False, hi=True)
dinn = np.column_stack([np.clip(dout[:, 0]-DOME_WALL, 0, None), dout[:, 1]])
dinn = dinn[dinn[:, 1] <= SEAT_Z - DOME_SOLID]              # 꼭대기 2mm 는 통짜 (축을 심을 살)
dome = vz(dome.difference(rev(np.vstack([[[0, Z0-4]], [[dinn[0, 0], Z0-4]], dinn,
                                        [[0, dinn[-1, 1]]]]))))
peg = cyl(PEG_R, PEG_H, (0, 0, SEAT_Z+PEG_H/2))             # 위로 솟은 축
peg = vz(peg.difference(box(20, 20, 20, (0, PEG_FLAT+10, SEAT_Z+PEG_H/2))))            # D컷
ch45 = tube_rev([[PEG_R-0.55, SEAT_Z+PEG_H], [PEG_R+3, SEAT_Z+PEG_H-3.55],
                 [PEG_R+3, SEAT_Z+PEG_H+3], [PEG_R-0.55, SEAT_Z+PEG_H+3]])
peg = vz(peg.difference(ch45))                              # 축 끝 45도 모따기 → 스스로 안내된다
dome = vz(dome.union(peg))
# 밴드에 꽂히는 립 + 립을 셸에 잇는 웹 (웹이 없으면 립이 따로 떨어져 나온다)
LIP_OUT = LIGHT_R - FIT_SLIDE                # 립을 헐렁하게 (넣기 쉽게)
lip = tube_rev([[LIGHT_R-1.6, Z0], [LIP_OUT, Z0], [LIP_OUT, Z0-LIP_D], [LIGHT_R-1.6, Z0-LIP_D]])
web = tube_rev([[LIGHT_R-1.6, Z0], [18.4-DOME_WALL+0.4, Z0], [18.4-DOME_WALL+0.4, Z0+1.0], [LIGHT_R-1.6, Z0+1.0]])
dome = vz(dome.union(lip)); dome = vz(dome.union(web))
for i in range(4):                           # 크러시 리브 : 0.15 만 물린다. 넣을 때 살짝 눌리고 그 뒤 안 빠진다
    rb = box(3.0, 1.4, LIP_D-0.9)
    rb.apply_translation([0, LIGHT_R+0.15-0.7, Z0-LIP_D/2-0.15])
    rb.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2*i+math.pi/4, [0, 0, 1]))
    dome = vz(dome.union(rb))
kb = box(KEY_W, 1.8, LIP_D-0.4)              # 방향키 (앞쪽 +Y = RED 명판 쪽). 한 방향으로만 들어간다
kb.apply_translation([0, LIGHT_R+0.55-0.9, Z0-LIP_D/2])
dome = vz(dome.union(kb))
# 정수리 : 오브 꽂이 소켓
FIN_PEG = 3.2
save(dome, "01_dome_WHITE")

# ═══════════════ 02 왕관 + 밴드 (레드, 한 몸) ═══════════════
bprof = np.vstack([
    [[SKIRT_R, -1.0]], [[SKIRT_R, SKIRT_TOP]],
    bez([[SKIRT_R, SKIRT_TOP], [SKIRT_R+1.4, SKIRT_TOP+1.2], [HEAD_R-0.5, 5.4], [HEAD_R, 6.6]], 26),
    [[HEAD_R, BAND_H-2.6]],
    bez([[HEAD_R, BAND_H-2.6], [HEAD_R, BAND_H-1.2], [HEAD_R-1.2, BAND_H-0.2], [HEAD_R-2.4, BAND_H]], 18)])
crown = rev(np.vstack([[[0, -1.0]], bprof, [[0, BAND_H]]]))
# 왕관 받침 : 밴드에서 곧게 세우고 위로 갈수록 살짝 벌어지게
cp = bez([[CUP_IN, BAND_H-1.8], [CUP_IN+0.3, BAND_H+3.0],
          [CUP_IN+0.6, BAND_H+12.0], [CUP_IN+0.9, BAND_H+CUP_UP]], 44)
wallsolid = shell(cp, CUP_T)                           # 스캘럽 자르기 전의 통짜 벽
crown = vz(crown.union(wallsolid))
for i in range(NPT):
    a = 2*math.pi*i/NPT; w = 2*math.pi/NPT
    crown = vz(crown.difference(scallop(a-w*0.5, a+w*0.5, BAND_H+CUP_UP+16,
                                        BAND_H+5.0, CUP_UP-5.0, 4.0, HEAD_R+12)))

# ── 뿔 보강 : 바늘 끝을 '첨탑'으로 바꿔 구슬 목을 없앤다 ──
#    v13 은 구슬 바로 밑 단면이 3.7mm2 뿐이라 툭 치면 층 사이가 떨어졌다.
#    실루엣(접선방향 폭)은 v13 처럼 날렵하게 두고, 반경방향 두께만 위로 갈수록 늘린다.
#    두께 증가는 9mm 에 1.4mm — 기울기 8도라 서포트가 전혀 필요없다.
BL_TOP = cp[-1, 1]
BL_BOT = BL_TOP - BLADE_L

def ring_pts(w, t, n=40):
    """반폭 w, 두께 t 인 스타디움 단면을 등간격 n점으로"""
    poly = stad(2*w, t)
    e = poly.exterior
    L = e.length
    return np.array([[p.x, p.y] for p in
                     (e.interpolate(L*k/n) for k in range(n))])

def pinnacle(a):
    zz = np.linspace(BL_BOT, BL_TOP, 22)
    s  = (zz - BL_BOT)/BLADE_L
    ww = BLADE_WB + (BLADE_WT-BLADE_WB)*np.power(s, 0.75)        # 접선 반폭 : 좁아짐
    tt = CUP_T   + (BLADE_T -CUP_T )*np.power(s, 1.25)           # 반경 두께 : 두꺼워짐
    ca, sa = math.cos(a), math.sin(a)
    rings = []
    for w, t, z in zip(ww, tt, zz):
        pq = ring_pts(w, t)
        rm = np.interp(z, cp[:, 1], cp[:, 0]) + CUP_T/2
        R = (rm + pq[:, 1])[:, None]*np.array([ca, sa]) + pq[:, 0][:, None]*np.array([-sa, ca])
        rings.append(np.column_stack([R, np.full(len(pq), z)]))
    return loft_rings(rings)

for i in range(NPT):
    crown = vz(crown.union(pinnacle(2*math.pi*i/NPT + math.pi/NPT)))

for i in range(NPT):                                   # 뿔 끝 구슬 (티어드롭)
    a = 2*math.pi*i/NPT + math.pi/NPT
    crown = vz(crown.union(teardrop(BEAD_R, ((cp[-1, 0]+CUP_T*0.5)*math.cos(a),
                                             (cp[-1, 0]+CUP_T*0.5)*math.sin(a), cp[-1, 1]-0.2))))
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
POK_HW = BOARD_W/2 + FIT_BOARD
pok = trimesh.creation.extrude_polygon(stad(POK_HW*2, POK_HW*2, POK_CR), Z_BTOP+2.0)
pok.apply_translation([0, 0, -2.0]); crown = vz(crown.difference(pok))                   # 보드+스프링 (아래로 열림)
crown = vz(crown.difference(frustum(POK_HW+CHAM, POK_HW, LID_T-0.01, LID_T+CHAM)))       # 입구 모따기
crown = vz(crown.difference(cyl(LIGHT_R, 80, (0, 0, Z_BTOP+40))))                       # 빛 구멍
crown = vz(crown.difference(tube_rev([[LIGHT_R-1.65, BAND_H], [LIGHT_R-0.1, BAND_H],
                                      [LIGHT_R-0.1, BAND_H-LIP_D-0.1], [LIGHT_R-1.65, BAND_H-LIP_D-0.1]])))
# 커넥터가 헤드 안에 없다. 보드 패드에 직접 납땜한 선 6가닥만 아래로 내려간다.
seat = trimesh.creation.extrude_polygon(stad(SEAT_HW*2, SEAT_HW*2, LID_CR), LID_T+1.35)  # 뚜껑 자리 (밑면까지 관통)
seat.apply_translation([0, 0, -1.2]); crown = vz(crown.difference(seat))
for i in range(2):                                                                       # 스냅 후크가 걸리는 홈 (뚜껑 자리 벽)
    sl = box(7.0, 1.8, 1.4, (0, SEAT_HW+0.7, 3.1))
    sl.apply_transform(trimesh.transformations.rotation_matrix(math.pi*i, [0, 0, 1]))
    crown = vz(crown.difference(sl))
crown = vz(crown.difference(box(KEY_W+0.8, 2.4, LIP_D+0.6,
                                (0, LIGHT_R+0.6, BAND_H-LIP_D/2-0.2))))   # 돔 방향키 홈
save(crown, "02_crown_RED")

# ═══════════════ 03 바닥 뚜껑 (레드) ═══════════════
lid = trimesh.creation.extrude_polygon(stad(LID_HW*2, LID_HW*2, LID_CR), LID_T)
lid = vz(lid.difference(cyl(BORE_R-0.3, LID_T*4, (0, 0, LID_T/2))))                      # 배선 관통
SPIG_R = HAND_R + 0.3
so = trimesh.creation.extrude_polygon(stad((SPIG_R+FIT_SLIDE)*2, (SPIG_R+FIT_SLIDE)*2), 2.0)  # 손잡이 스피곳 자리
so = vz(so.difference(cyl(BORE_R-0.3, 8.0, (0, 0, 1.0))))
lid = vz(lid.difference(so))
lid = vz(lid.difference(rev(np.array([[0, -0.01], [SPIG_R+FIT_SLIDE+CHAM, -0.01],
                                     [SPIG_R+FIT_SLIDE, CHAM], [0, CHAM]]))))            # 입구 모따기
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
    barb = box(6.2, BARB_OUT+0.55, 1.2, (0, LID_HW+(BARB_OUT-0.55)/2, 3.1))    # 걸림턱
    barb.apply_transform(T)
    lid = vz(lid.union(barb))
save(lid, "03_lid_RED")
print(f"  {'(BOOT/RESET)':22s} 뚜껑에 Ø{BTN_D} 접근 구멍만. 손잡이를 빼고 이쑤시개로 누른다")

# ═══════════════ 04 보드 밀어올림 스프링 (레드) ═══════════════
from shapely.geometry import LineString as SLine
sp2d = stad(SPR_OUT, SPR_OUT, 4.0).difference(SPt(0, 0).buffer(SPR_RIMIN, resolution=64))
tips = []
for i in range(4):
    a0 = math.radians(90*i + 8.0)
    t = np.linspace(0, 1, 40)
    th = a0 + t*math.radians(ARM_SWEEP)
    rr = ARM_R0 + t*(ARM_R1-ARM_R0)
    pts = np.column_stack([rr*np.cos(th), rr*np.sin(th)])
    sp2d = sp2d.union(SLine(pts).buffer(ARM_W/2, resolution=16, cap_style=1))
    sp2d = sp2d.union(SPt(pts[-1][0], pts[-1][1]).buffer(PAD_R, resolution=24))
    tips.append(pts[-1])
spring = trimesh.creation.extrude_polygon(sp2d, SPR_T)
for (tx, ty) in tips:                                        # 보드를 미는 기둥 (수직)
    bs = rev(np.array([[0, SPR_T], [BOSS_R, SPR_T], [BOSS_R, SPR_T+BOSS_H-0.25],
                       [BOSS_R-0.25, SPR_T+BOSS_H], [0, SPR_T+BOSS_H]]), 64)
    bs.apply_translation([tx, ty, 0]); spring = vz(spring.union(bs))
for i in range(4):                                           # 배선이 지나가는 얕은 홈 (관통 아님)
    a0 = math.radians(90*i + 45.0)
    wn = box(2.4, 12.0, 0.9, (0, 0, SPR_T-0.45))
    wn.apply_transform(trimesh.transformations.rotation_matrix(a0, [0, 0, 1]))
    wn.apply_translation([(SPR_RIMIN+1.6)*math.cos(a0), (SPR_RIMIN+1.6)*math.sin(a0), 0])
    spring = vz(spring.difference(wn))
spring.apply_translation([0, 0, Z_LID])
save(spring, "04_spring_RED")
_ov = spring.face_normals[:, 2] < -0.3
_zc = spring.triangles_center[:, 2] - spring.bounds[0][2]
print(f"  {'[스프링]':22s} 평판 {SPR_T}t · 팔 4개({ARM_SWEEP:.0f}도, {ARM_W}폭) · 눌림 {SPR_PUSH:.2f}mm "
      f"· 아래보는 면이 바닥 위에 있는 넓이 {spring.area_faces[_ov & (_zc > 0.15)].sum():.1f}mm2 (0 = 서포트 불필요)")

# ═══════════════ 05 손잡이 + 칼라 (레드) ═══════════════
hp = np.vstack([
      [[HAND_R-1.2, HAND_BOT]],
      bez([[HAND_R-1.2, HAND_BOT], [HAND_R-0.2, HAND_BOT], [HAND_R, HAND_BOT+0.6],
           [HAND_R, HAND_BOT+1.8]], 14),
      [[HAND_R, HAND_TOP-4.0]],
      bez([[HAND_R, HAND_TOP-3.4], [HAND_R+0.6, HAND_TOP-2.2], [HAND_R+1.4, HAND_TOP-1.2],
           [HAND_R+2.2, HAND_TOP]], 12),
      [[COL_TOP_R-1.0, -2.2]], [[COL_TOP_R, -1.0]]])
hand = rev(np.vstack([[[0, HAND_BOT]], hp, [[0, -1.0]]]))
hand = vz(hand.union(rev(np.array([[0, -1.0], [HAND_R+0.3, -1.0], [HAND_R+0.3, 1.7], [0, 1.7]]))))  # 스피곳
hand = vz(hand.difference(cyl(BORE_R, 260, (0, 0, HAND_BOT+BOT_WALL+130))))   # 바닥벽은 남긴다                                   # 구멍
for i in range(12):                                                                                 # 세로 홈
    a = 2*math.pi*i/12
    hand = vz(hand.difference(cyl(0.7, abs(HAND_TOP-HAND_BOT)*0.52,
                                  ((HAND_R+0.45)*math.cos(a), (HAND_R+0.45)*math.sin(a), (HAND_TOP+HAND_BOT)/2-6))))
dia = box(8.4, 2.4, 8.4)                                                                            # 마름모 엠블럼
dia.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4, [0, 1, 0]))
dia.apply_translation([0, HAND_R-0.6, HAND_TOP-4.5])
hand = vz(hand.union(dia))
# ═══ 전송 버튼 : 이제 스위치는 캐리어가 들고 있다. 손잡이는 관통구 + 뚜껑 자리만 ═══
YF = HAND_R
pad = trimesh.creation.extrude_polygon(stad(13.0, 12.0, 3.0), PAD_UP+2.0)
pad.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
pad.apply_translation([0, YF-2.0, SW_Z]); hand = vz(hand.union(pad))
hand = vz(hand.difference(cyl(BORE_R, 24.0, (0, 0, SW_Z))))      # 보스가 구멍을 먹지 않게 재관통
BZ_FLOOR = YF + PAD_UP - LIDT                       # 버튼 자리 바닥
rc = trimesh.creation.extrude_polygon(stad(LIDW, LIDW, 2.0), LIDT+2.0)
rc.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
rc.apply_translation([0, BZ_FLOOR, SW_Z]); hand = vz(hand.difference(rc))
hand = vz(hand.difference(cyl(BTN_HOLE/2, 9.0, (0, BZ_FLOOR-4.0, SW_Z), axis='y')))   # 벽 관통구
for sg in (1, -1):                                                                    # 버튼 걸림턱 홈
    hand = vz(hand.difference(box(1.6, 1.0, 3.8, (sg*LIDW/2, YF+PAD_UP-0.8, SW_Z))))
# 스트랩 귀 : 손잡이 옆으로 뻗는다  (구멍을 다시 메우지 않도록 자르기 전에 붙인다)
EAR_T, EAR_L = 4.4, 7.0
e2d = sbox(-3.7, -(HAND_R+EAR_L), 3.7, -HAND_R+3.4).buffer(-3.2, resolution=20).buffer(3.2, resolution=20)
ear = trimesh.creation.extrude_polygon(e2d, EAR_T)
ear.apply_translation([0, 0, HAND_BOT+1.4])
ear = vz(ear.difference(cyl(2.5, 12, (0, -(HAND_R+EAR_L-3.6), HAND_BOT+1.4+EAR_T/2))))
hand = vz(hand.union(ear))
# ── 아래쪽 내부 가공은 반드시 맨 마지막에 ──
#    v13/v14 는 구멍을 뚫은 뒤에 발과 귀를 union 해서 구멍을 도로 메웠다. 그래서 플러그가 못 들어갔다.
hand = vz(hand.difference(cyl(BORE_R, 16.0, (0, 0, HAND_BOT+BOT_WALL+8.0))))         # 구멍 재관통 (바닥벽은 남긴다)
hand = vz(hand.difference(tube_rev([[BORE_R, HAND_BOT+2.6], [BORE_R+0.75, HAND_BOT+2.6],
                                    [BORE_R+0.75, HAND_BOT+4.2], [BORE_R, HAND_BOT+4.2]])))  # 접착제 링홈
# 바닥 : 플러그 오버몰드 자리 + 플러그 구멍 + 방향키 핀 구멍
MOUTH_Y = -(SK_SH+SK_PT+0.5)/2 + SK_PT + SK_SH/2
sink = trimesh.creation.extrude_polygon(stad(12.6, 6.6, 3.0), BOT_SINK+0.02)
sink.apply_translation([0, MOUTH_Y, HAND_BOT-0.01]); hand = vz(hand.difference(sink))
ap = trimesh.creation.extrude_polygon(stad(PLUG_W+0.35, PLUG_H+0.35, (PLUG_H+0.35)/2-0.02),
                                      BOT_WALL+0.1)
ap.apply_translation([0, MOUTH_Y, HAND_BOT+BOT_SINK-0.05]); hand = vz(hand.difference(ap))
hand = vz(hand.difference(box(KEY_RD+0.6, KEY_RW+0.4, 200,                          # 방향키 홈 (+x, 전 길이)
                              (BORE_R+(KEY_RD+0.6)/2-0.1, 0, HAND_BOT+BOT_WALL+100))))
# 구멍 안쪽 접착제 링홈 (본드가 고여 링이 되어 캐리어를 붙잡는다)
hand = vz(hand.difference(tube_rev([[BORE_R, HAND_BOT+7.0], [BORE_R+0.8, HAND_BOT+7.0],
                                    [BORE_R+0.8, HAND_BOT+9.0], [BORE_R, HAND_BOT+9.0]])))
save(hand, "05_handle_RED")

# ═══════════════ 07 캐리어 : USB 포트 + 택트 스위치를 한 몸에 (레드) ═══════════════
#  손잡이 위에서 밀어 넣는다. 전기 부품 전부를 책상에서 조립·납땜·테스트하고 나서 꽂는다.
#  아래 = 포트 스테이션, 위 = 스위치 스테이션, 사이 = C자 척추(선이 그 안으로 지나감).
#  C자라서 살짝 벌어지려는 힘이 있어 스위치 쪽 면이 구멍 벽에 밀착된다 → 버튼 높이가 결정된다.
CR_R    = BORE_R - FIT_SLIDE                       # 캐리어 반지름
CR_BOT  = HAND_BOT + BOT_WALL                      # 캐리어 밑면 = 손잡이 바닥벽 안쪽
POC_W, POC_H = SK_PW + 0.5, SK_SH + SK_PT + 0.5    # 커넥터 자리
MOUTH_Y = -POC_H/2 + SK_PT + SK_SH/2               # 리셉터클 입구 중심
TAIL_H  = SK_PT + 1.8
TAIL_Y  = -POC_H/2 + TAIL_H/2
PORT_TOP = CR_BOT + SK_SL                          # 커넥터 셸 뒷면 = 밀어넣는 힘을 받는 턱
CR_TOP  = SW_Z + 6.5

SWF_Y   = math.sqrt(CR_R**2 - (SW_W/2+FIT_SLIDE)**2)   # 스위치 앞면 — 원 안에 자리가 들어가는 한계
SWB_Y   = SWF_Y - SW_DEEP                              # 몸통 뒷면 (받침)
SWL_Y   = SWB_Y - SW_LEGL                              # 다리 슬롯 바닥
WIRE_W, WIRE_H = 8.0, 3.6
WIRE_Y  = SWL_Y - 1.3 - WIRE_H/2                       # 배선 슬롯 중심

car = cyl(CR_R, CR_TOP-CR_BOT, (0, 0, (CR_BOT+CR_TOP)/2))
# ── 포트 스테이션 ──
car = vz(car.difference(box(POC_W, POC_H, SK_SL+0.02, (0, 0, CR_BOT+SK_SL/2))))
car = vz(car.difference(box(POC_W, TAIL_H, 40, (0, TAIL_Y, PORT_TOP+20))))          # 꼬리 + 선

# ── C자 척추 : 선이 지나가는 통로. 벽 1.6 ──
SPINE_LO, SPINE_HI = PORT_TOP + 2.4, SW_Z - 5.0
car = vz(car.difference(cyl(CR_R-1.6, SPINE_HI-SPINE_LO, (0, 0, (SPINE_LO+SPINE_HI)/2))))
car = vz(car.difference(box(9.6, 8.0, SPINE_HI-SPINE_LO, (0, -CR_R-4.0+3.4, (SPINE_LO+SPINE_HI)/2))))
# ── 스위치 스테이션 ──
car = vz(car.difference(box(SW_W+FIT_SLIDE*2, SW_DEEP+2.0, SW_W+FIT_SLIDE*2,
                            (0, (SWF_Y+SWB_Y)/2+1.0, SW_Z))))                       # 몸통 자리
car = vz(car.difference(box(SW_LEGS+FIT_SLIDE*2+1.0, SW_LEGL, SW_LEGS+FIT_SLIDE*2+1.0,
                            (0, (SWB_Y+SWL_Y)/2, SW_Z))))                           # 다리 사방 릴리프
car = vz(car.difference(box(WIRE_W, WIRE_H, 60, (0, WIRE_Y, SW_Z))))                # 배선 슬롯
for sg in (1, -1):                                                                  # 크러시 리브 : 스위치를 물어준다
    car = vz(car.union(box(0.8, SW_DEEP-1.2, 2.6,
                           (sg*(SW_W/2+FIT_SLIDE-0.03), (SWF_Y+SWB_Y)/2+0.4, SW_Z))))
car = vz(car.difference(rev(np.array([[0, CR_TOP-0.01], [CR_R, CR_TOP-0.01],
                                      [CR_R-0.8, CR_TOP-0.8], [0, CR_TOP-0.8]]))))  # 위끝 모따기 (거꾸로)
for (z0, z1) in [(CR_BOT+0.6, CR_BOT+SK_SL+2.0), (SW_Z-5.0, CR_TOP-1.0)]:            # 방향키 리브
    kr = box(1.6, KEY_RW, z1-z0, (CR_R-0.8+KEY_RD, 0, (z0+z1)/2))
    ktip = rev(np.array([[0, z0-0.01], [CR_R+KEY_RD+1, z0-0.01],
                         [CR_R+KEY_RD+1, z0+0.7], [CR_R-0.4, z0-0.01]]), 64, lo=False, hi=False)
    car = vz(car.union(vz(kr.difference(box(4, 4, 1.6, (CR_R+KEY_RD+1.0, 0, z0+0.3))))))
save(car, "07_carrier_RED")

# ═══════════════ 10 공차 테스트 쿠폰 (레드) — 10분이면 뽑힌다 ═══════════════
g = trimesh.creation.extrude_polygon(stad(74.0, 34.0, 4.0), 3.0)
gp = trimesh.creation.extrude_polygon(stad(POK_HW*2, POK_HW*2, 6.0), 9.0)
gp.apply_translation([-21.0, 0, -0.5]); g = vz(g.difference(gp))                     # 보드 자리
gs = trimesh.creation.extrude_polygon(stad(SPIG_R*2, SPIG_R*2, 6.0), 3.2)
gs.apply_translation([9.0, 0, 3.0]); g = vz(g.union(gs))                             # 뚜껑 소켓 시험용 스피곳
g = vz(g.difference(cyl(BORE_R-0.3, 12.0, (9.0, 0, 3.0))))
stub = vz(car.intersection(box(40, 40, 15.0, (0, 0, SW_Z))))                         # 스위치 자리 실물 복제
stub.apply_translation([0, 0, -SW_Z + 3.0])
stub.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
stub.apply_translation([28.0, 0, 3.0]); g = vz(g.union(stub))
g = vz(g.difference(box(60, 60, 20, (28.0, 0, -10.0+0.001))))
save(g, "10_fitgauge_RED")
print(f"  {'[게이지]':22s} 보드 자리 / 스피곳 / ★스위치 자리 복제 — 실물로 끼워볼 것")
print(f"  {'[캐리어]':22s} 길이 {CR_TOP-CR_BOT:.1f} · 스위치 앞면 y{SWF_Y:.2f} "
      f"(스템끝 y{SWF_Y+1.2:.2f} < 구멍벽 {BORE_R}) · 배선 슬롯 {WIRE_W}x{WIRE_H} "
      f"· 턱 {min(POC_W,SK_SW)*(POC_H/2-(TAIL_Y+TAIL_H/2)):.1f}mm2")

# ═══════════════ 06 버튼 (레드) ═══════════════
#  스위치가 구멍 안 캐리어에 있으므로, 버튼이 플런저를 갖고 벽을 지나 스템을 누른다.
#  걸림턱이 1.0 높이 홈 안에서 놀아 0.5 만큼 눌린다 (스위치 행정 0.25 + 틈 0.15).
CAPW = LIDW - FIT_SLIDE*2
STEM_TOP = SWF_Y + 1.2                                    # 스템 끝 (캐리어 기준)
BOSS_LEN = BZ_FLOOR - (STEM_TOP + 0.15)                   # 플런저 길이
btn = trimesh.creation.extrude_polygon(stad(CAPW, CAPW, 2.0), LIDT)
btn = vz(btn.union(rev(np.array([[0, -BOSS_LEN], [BTN_BOSS/2-0.5, -BOSS_LEN],
                                 [BTN_BOSS/2, -BOSS_LEN+0.5], [BTN_BOSS/2, 0.2], [0, 0.2]]), 96)))
for sg in (1, -1):                                                                   # 걸림턱
    btn = vz(btn.union(box(1.5, 3.6, 0.7, (sg*(CAPW/2+0.15), 0, LIDT-0.55))))
btn.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
btn.apply_translation([0, BZ_FLOOR, SW_Z])
save(btn, "06_button_RED")
print(f"  {'[버튼]':22s} 플런저 Ø{BTN_BOSS} x {BOSS_LEN:.2f} · 스템끝 y{STEM_TOP:.2f} "
      f"· 여유 0.15 + 행정 0.25 = 0.40 (홈 1.0)")

# ═══════════════ 08 오브(피니얼) + 09 십자가 (레드) ═══════════════
ORB_R = 4.8
Z_APEX = Z0 + DOME_H
ORB_Z = Z_APEX + 2.2 + ORB_R
FIN_BOT = SEAT_Z                                                    # 돔 자리 위에 그대로 앉는다
fin = rev(np.array([[0, FIN_BOT], [DOME_SEAT_R, FIN_BOT], [DOME_SEAT_R, FIN_BOT+3.2],
                    [3.4, Z_APEX+3.5], [1.8, ORB_Z], [0, ORB_Z]]))
orb = trimesh.creation.icosphere(subdivisions=3, radius=ORB_R); orb.apply_translation([0, 0, ORB_Z])
fin = vz(trimesh.boolean.union([vz(fin), vz(orb)]))
# 돔 축이 들어가는 D컷 소켓 (한 방향으로만 들어간다 → 십자가가 저절로 정면을 본다)
SOCK_R, SOCK_D = PEG_R+FIT_PRESS, PEG_H+0.4
sk = cyl(SOCK_R, SOCK_D*2, (0, 0, FIN_BOT+SOCK_D-0.01))
sk = vz(sk.difference(box(20, 20, 20, (0, PEG_FLAT+FIT_PRESS+10, FIN_BOT+SOCK_D))))
fin = vz(fin.difference(sk))
fin = vz(fin.difference(rev(np.array([[0, FIN_BOT-0.01], [SOCK_R+0.6, FIN_BOT-0.01],
                                     [SOCK_R, FIN_BOT+0.6], [0, FIN_BOT+0.6]]))))        # 입구 모따기
# 돔을 깎아낼 필요가 없어졌다 — 피니얼 밑면이 돔 평면 위에 그대로 앉는다
CR = dict(t=3.6, a=2.2, b=2.8, lx=6.5, up=8.5, dn=5.0, peg=6.0, fil=0.9)
CROSS_Z = ORB_Z + ORB_R - 1.0
SLW, SLT = CR['a']*2+FIT_PRESS*2, CR['t']+FIT_PRESS*2
fin = vz(fin.difference(box(SLW, SLT, CR['peg']+6.0, (0, 0, CROSS_Z-CR['peg']/2+2.0))))
# 슬롯 입구는 오브가 구면이라 이미 깔때기처럼 벌어져 있다. 인위적으로 더 벌리면 오브가 잘린다.
save(fin, "08_finial_RED")

arms = []
for dx, dy, L in [(1,0,CR['lx']), (-1,0,CR['lx']), (0,1,CR['up']), (0,-1,CR['dn'])]:
    px, py = -dy, dx
    arms.append(SPoly([(px*CR['a'], py*CR['a']), (dx*L+px*CR['b'], dy*L+py*CR['b']),
                       (dx*L-px*CR['b'], dy*L-py*CR['b']), (-px*CR['a'], -py*CR['a'])]))
cpo = unary_union(arms).buffer(CR['fil'], resolution=16).buffer(-CR['fil'], resolution=16)
cpo = cpo.buffer(0.5, resolution=16).buffer(-0.5, resolution=16)
PEG_TIP = CR['a'] - 0.65                                       # 꽂이 끝을 좁혀 스스로 들어가게
cpo = cpo.union(sbox(-CR['a'], -CR['dn']-CR['peg']+1.0, CR['a'], -CR['dn']+1.0))
cpo = cpo.union(SPoly([(-CR['a'], -CR['dn']-CR['peg']+1.0), (CR['a'], -CR['dn']-CR['peg']+1.0),
                       (PEG_TIP, -CR['dn']-CR['peg']), (-PEG_TIP, -CR['dn']-CR['peg'])]))
cross_flat = trimesh.creation.extrude_polygon(cpo, CR['t']); cross_flat.apply_translation([0, 0, -CR['t']/2])
save(cross_flat, "09_cross_RED")
cross = cross_flat.copy()
cross.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]))
cross.apply_translation([0, 0, CROSS_Z + CR['dn']]); cross = vz(cross)
cross.export(f"{OUT}/_cross_placed.stl")

TOTAL = (CROSS_Z + CR['dn'] + CR['up']) - HAND_BOT
print(f"\n  전장 {TOTAL:.1f}mm · 헤드 Ø{HEAD_R*2:.0f} · 손잡이 Ø{HAND_R*2:.0f}(구멍 Ø{BORE_R*2:.0f}) · 밴드 {BAND_H:.1f}mm")
