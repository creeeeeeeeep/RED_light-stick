"""
red_head_v24.py — 머리(돔 · 왕관 · 첨탑 · 십자) 전체를 처음부터 다시  (독립 스크립트)
손잡이·캐리어는 red_v23.py.  겉모양은 v19 그대로, '끼우는 자리' 는 전부 FDM 기준으로 다시 설계했다.

왜 안 들어갔나 (v19 ~ v21b 돔 ↔ 왕관)
  1. 돔 밑이 허공에 떠서 인쇄됐다. 립(Ø30)만 베드에 닿고, 돔 벽·웹(Ø37)은 2.6mm 위 허공 → 처진다
     → 처진 살이 왕관 바닥에 먼저 닿아 돔이 끝까지 안 내려간다 → 러그가 홈 높이에 못 간다
  2. 러그도 베드에서 0.3 떠 있었다 → 밑이 처져 두꺼워진다
  3. 왕관 홈 천장이 수평 오버행이고 두께가 0.3~0.75mm 뿐 → 처지고, 얇아서 휜다
  4. 디텐트(돌기)를 넘어야 돌아갔다
  반경 공차(0.35 → 0.55)만 키워서는 해결이 안 되는 문제들이었다.

v24 이음부
  · 돔 벽이 그대로 2.6mm 내려가 '치마' 가 된다 → 돔 밑 전체가 베드에 닿는다. 허공에 뜨는 면 0
  · 왕관에는 그 치마가 들어가는 넓은 자리(Ø37.9). 러그는 치마 바깥에, 베드에 붙어서
  · 홈 천장 = 45도 (서포트 없이 정확히 나온다). 천장 위 살 1.2mm 이상
  · 러그 윗면도 45도. 디텐트 없음. 30도 돌리면 끝벽에 닿아 멈춘다 (십자가가 정면)
  · 천장이 끝으로 갈수록 0.4 낮아진다 → 돌릴수록 돔이 눌려 덜 논다
  · 반경 틈 0.55, 진입 홈 좌우 3도, 입구 모따기, 코끼리발 도피
"""
import numpy as np, math, os, trimesh
from shapely.geometry import Polygon as SPoly, box as sbox
from shapely.ops import unary_union
from shapely.affinity import translate as stranslate

OUT = "/home/claude/v24"; os.makedirs(OUT, exist_ok=True)
SEG = 160

# ═══════════ 보드 · 적층 (v19 ~ v21b 그대로) ═══════════
BOARD_W, BOARD_T = 25.27, 5.5     # ★ 2026-11-14 실측 25.27 x 25.25. 기판+LED 2.5 · 밑면 USB 커넥터 3.2
                                  #   BOARD_T 는 '보드 자리 깊이' 로만 쓰인다 (천장 z 9.7 = 기판 윗면 모서리)
FIT_BOARD = 0.45                  # 보드 자리 편측
FIT_SEAT  = 0.45                  # ★ 손잡이 플러그 자리 편측 (0.35 → 0.45, + 입구 모따기)
FIT_PEG   = 0.30                  # ★ 첨탑·십자 꽂이 (0.25 → 0.30)
CHAM      = 0.6
LID_HW, LID_CR = 14.15, 8.0       # 손잡이 플러그 28.3각
SEAT_HW   = LID_HW + FIT_SEAT
HEAD_R    = 23.5
LID_T, PAD_H, TAB_T, LIP_D = 2.6, 1.6, 1.6, 2.6
BAND_H    = LID_T + PAD_H + BOARD_T + TAB_T + LIP_D          # 13.9
LIGHT_R   = 15.5                  # 빛 구멍
CUP_IN, CUP_T, CUP_UP = 20.6, 2.6, 20.0
BEAD_R    = 2.7
BLADE_L, BLADE_WT, BLADE_WB, BLADE_T = 10.0, 1.75, 3.55, 4.10
NPT       = 8
DOME_MAX, DOME_H, DOME_WALL = 19.6, 29.0, 1.6
DOME_SEAT_R, DOME_SOLID = 4.4, 2.0
PEG_R, PEG_H, PEG_FLAT = 2.40, 3.4, 1.60
SKIRT_R, SKIRT_TOP, POK_CR = 19.5, 2.0, 1.2     # ★ SKIRT_TOP 3.4 → 2.0 : 밴드 밑 곡면을 45도 이하로 (서포트 없이 깨끗하게)
CROWN_BOT = -1.0
EF        = 0.4                   # 코끼리발 도피

Z0     = BAND_H                   # 왕관 컵 바닥 = 돔이 보이기 시작하는 높이
Z_BRD  = LID_T + PAD_H            # 보드 밑면 4.2
Z_BTOP = Z_BRD + BOARD_T          # 보드 윗면 9.7

# ═══════════ ★ 돔 ↔ 왕관 이음부 ═══════════
DOME_R0  = 18.4                   # 돔 밑 바깥 반지름 (치마도 같은 값)
FIT_DOME = 0.55                   # 반경 틈 (넣고 돌리는 자리)
SK_BOT   = Z0 - LIP_D             # 11.3  치마 밑 = 왕관 자리 바닥 (돔이 앉는 유일한 면)
CB_R     = DOME_R0 + FIT_DOME     # 18.95 왕관 자리 반지름
BAY_N, BAY_W, BAY_TURN = 3, 26.0, 30.0
LUG_OUT  = 1.1
LUG_R    = DOME_R0 + LUG_OUT      # 19.5
LUG_V    = 0.5                    # 러그 바깥 수직면 높이. 그 위는 45도
GRV_R    = LUG_R + FIT_DOME       # 20.05 (컵 안벽 20.6 보다 안쪽)
GRV_FL   = SK_BOT - 0.2           # 홈 바닥은 0.2 더 깊다 → 러그 밑은 절대 안 닿는다 (앉는 면은 하나)
AX_LOCK, AX_IN = 0.30, 0.65       # 러그 위 틈 : 잠긴 끝 0.30 → 진입 쪽 0.65 (돌릴수록 덜 논다. 끼지는 않는다)
ENT_MARG = 3.0                    # 진입 홈 좌우 여유 (도)
STOP_MARG = 0.6                   # 끝벽 여유 (도)

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
def shell(prof, t):
    P = np.asarray(prof, float)
    return tube_rev(np.vstack([P, np.column_stack([P[:, 0]+t, P[:, 1]])[::-1]]))
def box(sx, sy, sz, pos=(0, 0, 0)):
    b = trimesh.creation.box((sx, sy, sz)); b.apply_translation(pos); return b
def cyl(r, h, pos=(0, 0, 0), n=96):
    c = trimesh.creation.cylinder(radius=r, height=h, sections=n); c.apply_translation(pos); return c
def stad(w, d, r=None):
    if r is None: r = min(w, d)/2 - 0.15
    return sbox(-w/2, -d/2, w/2, d/2).buffer(-r, resolution=24).buffer(r, resolution=24)
def ext(poly, z0, z1):
    m = trimesh.creation.extrude_polygon(poly, z1-z0); m.apply_translation([0, 0, z0]); return vz(m)
def sweep(th0, th1, loopf, n=48):
    """(r, z) 볼록 단면을 th0 → th1 (도) 로 쓸어 만든 부채꼴. loopf(t) 로 단면을 각도에 따라 바꿀 수 있다"""
    f = loopf if callable(loopf) else (lambda t: loopf)
    K = len(f(0.0)); V = []; F = []
    for j in range(n):
        t = j/(n-1); a = math.radians(th0 + (th1-th0)*t); c, s = math.cos(a), math.sin(a)
        for (r, z) in f(t): V.append([r*c, r*s, z])
    for j in range(n-1):
        A, B = K*j, K*(j+1)
        for q in range(K):
            q2 = (q+1) % K; F.append([A+q, A+q2, B+q2]); F.append([A+q, B+q2, B+q])
    A = K*(n-1)
    for q in range(1, K-1): F.append([0, q+1, q]); F.append([A, A+q, A+q+1])
    return vz(trimesh.Trimesh(np.array(V), np.array(F), process=True))
def arc(th0, th1, r0, r1, z0, z1, n=48):
    return sweep(th0, th1, [(r0, z0), (r1, z0), (r1, z1), (r0, z1)], n)
def scallop(th0, th1, ztop, zdip, h, r_in, r_out, p=1.8, M=26):
    s = np.linspace(0, 1, M); th = th0 + s*(th1-th0)
    zb = zdip + h*np.power(np.abs(2*s-1), p); V, F = [], []
    for k in range(M):
        c, sn = math.cos(th[k]), math.sin(th[k])
        for (r, z) in [(r_in, zb[k]), (r_out, zb[k]), (r_out, ztop), (r_in, ztop)]: V.append([r*c, r*sn, z])
    for k in range(M-1):
        a, b = 4*k, 4*(k+1)
        for q in range(4):
            q2 = (q+1) % 4; F.append([a+q, a+q2, b+q2]); F.append([a+q, b+q2, b+q])
    F += [[0, 2, 1], [0, 3, 2]]; a = 4*(M-1); F += [[a, a+1, a+2], [a, a+2, a+3]]
    return vz(trimesh.Trimesh(np.array(V), np.array(F), process=True))
def loft_rings(rings):
    N = len(rings[0]); K = len(rings); V = [v for R in rings for v in R.tolist()]; F = []
    for k in range(K-1):
        for i in range(N):
            j = (i+1) % N
            F.append([k*N+i, k*N+j, (k+1)*N+j]); F.append([k*N+i, (k+1)*N+j, (k+1)*N+i])
    c0 = len(V); V.append(np.mean(rings[0], axis=0).tolist())
    for i in range(N): F.append([c0, (i+1) % N, i])
    c1 = len(V); V.append(np.mean(rings[-1], axis=0).tolist()); b = (K-1)*N
    for i in range(N): F.append([c1, b+i, b+(i+1) % N])
    return vz(trimesh.Trimesh(np.array(V), np.array(F), process=True))
def ray_ring(poly, z, n=96):
    """중심에서 같은 각도로 쏜 점들 → 크기가 다른 두 윤곽을 꼬임 없이 잇는다"""
    from shapely.geometry import LineString
    P = []
    for k in range(n):
        a = 2*math.pi*k/n; p = poly.exterior.intersection(LineString([(0, 0), (60*math.cos(a), 60*math.sin(a))]))
        P.append([p.x, p.y, z])
    return np.array(P)
def taper(poly, grow, z0, z1):
    """z0 에서 grow 만큼 넓고 z1 에서 원래 크기인 깔때기 (입구 모따기용)"""
    return loft_rings([ray_ring(poly.buffer(grow, resolution=24), z0), ray_ring(poly, z1)])
def sq_ring(h, n=48):
    m = n//4; t = np.linspace(0, 1, m, endpoint=False); P = []
    P += [[-h+2*h*u, -h] for u in t]; P += [[h, -h+2*h*u] for u in t]
    P += [[h-2*h*u, h] for u in t];   P += [[-h, h-2*h*u] for u in t]
    return np.array(P)
def frustum(h0, h1, z0, z1, n=48):
    return loft_rings([np.column_stack([sq_ring(h0, n), np.full(n, z0)]), np.column_stack([sq_ring(h1, n), np.full(n, z1)])])
def teardrop(r, pos):
    s = trimesh.creation.icosphere(subdivisions=2, radius=r)
    c = rev(np.array([[0, -r*1.35], [r*0.999, 0.0], [0, 0.0]]), 48)
    m = vz(trimesh.boolean.union([vz(s), vz(c)])); m.apply_translation(pos); return m
def text_poly(s, size):
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    tp = TextPath((0, 0), s, size=size, prop=FontProperties(family='DejaVu Sans', weight='bold'))
    polys = sorted([SPoly(np.asarray(p)).buffer(0) for p in tp.to_polygons() if len(p) > 2], key=lambda p: -p.area)
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
    return m
def rotz(m, deg):
    m = m.copy(); m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(deg), [0, 0, 1])); return m
def mv(m, d): m = m.copy(); m.apply_translation(d); return m
def D(a, b): return vz(a.difference(b))
def U(a, b): return vz(a.union(b))
def I(a, b): return vz(a.intersection(b))
def save(m, name, expect=1):
    m = vz(m); cs = m.split(only_watertight=False)
    if len(cs) > expect:
        keep = [c for c in cs if abs(c.volume) > 0.5]
        if len(keep) == expect: m = trimesh.util.concatenate(keep)
    m.export(f"{OUT}/{name}.stl"); e = m.bounds[1]-m.bounds[0]; nb = len(m.split(only_watertight=False))
    print(f"  {name:18s} {e[0]:5.1f} x {e[1]:5.1f} x {e[2]:5.1f}  {m.volume/1000:5.2f}cm3  wt={m.is_watertight}  "
          f"덩어리 {nb}{'' if nb == expect else '  ⚠ 예상 '+str(expect)}")
    return m

print("RED v24 — 머리 (돔 · 왕관 · 첨탑 · 십자)\n")

# ═══════════════════ 01 돔 ═══════════════════
SEAT_Z = Z0 + DOME_H - 2.6                                  # 첨탑이 앉는 평면
dout = bez([[DOME_R0, Z0], [DOME_MAX+0.6, Z0+8], [17.0, Z0+22], [DOME_SEAT_R, SEAT_Z]], 80)
dome = rev(np.vstack([[[0, SK_BOT]], [[DOME_R0, SK_BOT]], dout]), lo=False, hi=True)      # ★ 벽이 치마로 곧게 내려간다
dinn = np.column_stack([np.clip(dout[:, 0]-DOME_WALL, 0, None), dout[:, 1]])
dinn = dinn[dinn[:, 1] <= SEAT_Z - DOME_SOLID]
dome = D(dome, rev(np.vstack([[[0, SK_BOT-4]], [[dinn[0, 0], SK_BOT-4]], dinn, [[0, dinn[-1, 1]]]])))
# ★ 첨탑을 돔과 한 몸으로 (2026-11-14 정수 : 돔↔첨탑 꽂이(Ø4.8 축)가 너무 잘 부러진다 → 꽂이를 없앴다)
#   십자만 따로 — 눕혀서 뽑아야 하므로. 첨탑 색을 다르게 하려면 슬라이서에서 '높이에서 필라멘트 교체' 를 FIN_BOT 높이에 건다.
ORB_R = 4.8; Z_APEX = Z0 + DOME_H; ORB_Z = Z_APEX + 2.2 + ORB_R; FIN_BOT = SEAT_Z
CR = dict(t=3.6, a=2.2, b=2.8, lx=6.5, up=8.5, dn=5.0, peg=6.0, fil=0.9)
CROSS_Z = ORB_Z + ORB_R - 1.0
SLW, SLT = CR['a']*2+FIT_PEG*2, CR['t']+FIT_PEG*2
fin = rev(np.array([[0, FIN_BOT-1.0], [DOME_SEAT_R, FIN_BOT-1.0], [DOME_SEAT_R, FIN_BOT+3.2], [3.9, Z_APEX+3.5], [1.8, ORB_Z], [0, ORB_Z]]))   # 목을 3.4 → 3.9 로 굵게
orb = trimesh.creation.icosphere(subdivisions=3, radius=ORB_R); orb.apply_translation([0, 0, ORB_Z])
fin = vz(trimesh.boolean.union([vz(fin), vz(orb)]))
fin = D(fin, box(SLW, SLT, CR['peg']+6.0, (0, 0, CROSS_Z-CR['peg']/2+2.0)))                 # 십자 꽂이 홈
dome = U(dome, fin)
dome = D(dome, tube_rev([[DOME_R0-EF, SK_BOT-0.01], [DOME_R0+1, SK_BOT-0.01], [DOME_R0+1, SK_BOT+EF+1]]))   # 치마 밑 모따기
lug_loop = [(DOME_R0-0.3, SK_BOT), (LUG_R, SK_BOT), (LUG_R, SK_BOT+LUG_V), (DOME_R0-0.3, SK_BOT+LUG_V+LUG_OUT+0.3)]
for i in range(BAY_N):                                                                    # 러그 (베드에 붙고, 윗면 45도)
    a0 = 90.0 + 360.0*i/BAY_N
    dome = U(dome, sweep(a0-BAY_W/2, a0+BAY_W/2, lug_loop, 24))
dome = D(dome, tube_rev([[LUG_R-EF, SK_BOT-0.01], [LUG_R+1, SK_BOT-0.01], [LUG_R+1, SK_BOT+EF+1]]))         # 러그 밑 모따기
dome = save(dome, "01_dome_CLEAR")

# ═══════════════════ 02 왕관 ═══════════════════
bprof = np.vstack([
    [[SKIRT_R-EF, CROWN_BOT]], [[SKIRT_R, CROWN_BOT+EF]], [[SKIRT_R, SKIRT_TOP]],          # ★ 밑 모서리 모따기 (이음선이 깔끔해진다)
    bez([[SKIRT_R, SKIRT_TOP], [SKIRT_R+0.4, SKIRT_TOP+1.0], [HEAD_R-0.4, 5.6], [HEAD_R, 6.6]], 26),   # 가운데가 정확히 45도
    [[HEAD_R, BAND_H-2.6]],
    bez([[HEAD_R, BAND_H-2.6], [HEAD_R, BAND_H-1.2], [HEAD_R-1.2, BAND_H-0.2], [HEAD_R-2.4, BAND_H]], 18)])
crown = rev(np.vstack([[[0, CROWN_BOT]], bprof, [[0, BAND_H]]]))
cp = bez([[CUP_IN, BAND_H-1.8], [CUP_IN+0.3, BAND_H+3.0], [CUP_IN+0.6, BAND_H+12.0], [CUP_IN+0.9, BAND_H+CUP_UP]], 44)
crown = U(crown, shell(cp, CUP_T))
for i in range(NPT):
    a = 2*math.pi*i/NPT; w = 2*math.pi/NPT
    crown = D(crown, scallop(a-w*0.5, a+w*0.5, BAND_H+CUP_UP+16, BAND_H+5.0, CUP_UP-5.0, 4.0, HEAD_R+12))
BL_TOP = cp[-1, 1]; BL_BOT = BL_TOP - BLADE_L
def ring_pts(w, t, n=40):
    e = stad(2*w, t).exterior; L = e.length
    return np.array([[p.x, p.y] for p in (e.interpolate(L*k/n) for k in range(n))])
def pinnacle(a):
    zz = np.linspace(BL_BOT, BL_TOP, 22); s = (zz - BL_BOT)/BLADE_L
    ww = BLADE_WB + (BLADE_WT-BLADE_WB)*np.power(s, 0.75); tt = CUP_T + (BLADE_T-CUP_T)*np.power(s, 1.25)
    ca, sa = math.cos(a), math.sin(a); rings = []
    for w, t, z in zip(ww, tt, zz):
        pq = ring_pts(w, t); rm = np.interp(z, cp[:, 1], cp[:, 0]) + CUP_T/2
        R = (rm + pq[:, 1])[:, None]*np.array([ca, sa]) + pq[:, 0][:, None]*np.array([-sa, ca])
        rings.append(np.column_stack([R, np.full(len(pq), z)]))
    return loft_rings(rings)
for i in range(NPT):
    a = 2*math.pi*i/NPT + math.pi/NPT
    crown = U(crown, pinnacle(a))
    crown = U(crown, teardrop(BEAD_R, ((cp[-1, 0]+CUP_T*0.5)*math.cos(a), (cp[-1, 0]+CUP_T*0.5)*math.sin(a), cp[-1, 1]-0.2)))
    zc = BAND_H + 3.4; r = np.interp(zc, cp[:, 1], cp[:, 0]) + CUP_T                       # 마름모 문양
    d = box(6.4, 2.0, 6.4); d.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4, [0, 1, 0]))
    d.apply_translation([0, r-0.5, zc]); d.apply_transform(trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
    crown = U(crown, d)
PLY = HEAD_R - 1.2                                                                         # RED 명판
plate = box(19.0, 5.0, 6.4, (0, PLY, 9.0))
ch = box(30, 30, 30); ch.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4, [1, 0, 0]))
ch.apply_translation([0, PLY+2.5-21.2, 9.0-3.2-21.2])
crown = U(crown, D(plate, ch))
# ★ 이름은 음각 : 명판 앞면에서 ENG_D 만큼 파낸다. 검정 조각(02c)은 파인 자리 바닥에 깔리는 0.4mm
ENG_D, ENG_INK = 0.8, 0.4
_tp = text_poly("RED", 5.6)
for c in emboss(_tp, ENG_D+0.2, PLY+2.5+0.2, 9.0).split(only_watertight=False):
    crown = D(crown, vz(c))
letters = trimesh.util.concatenate([vz(c) for c in emboss(_tp, ENG_INK, PLY+2.5-ENG_D+ENG_INK, 9.0).split(only_watertight=False)])
# ── 안쪽 (전부 맨 마지막에 판다) ──
POK_HW = BOARD_W/2 + FIT_BOARD
crown = D(crown, ext(stad(POK_HW*2, POK_HW*2, POK_CR), -2.0, Z_BTOP))                       # 보드 자리 (아래로 열림)
crown = D(crown, frustum(POK_HW+CHAM, POK_HW, LID_T-0.01, LID_T+CHAM))                      # 보드 입구 모따기
crown = D(crown, cyl(LIGHT_R, 80, (0, 0, Z_BTOP+40-0.01)))                                  # 빛 구멍
seat2d = stad(SEAT_HW*2, SEAT_HW*2, LID_CR+FIT_SEAT)
crown = D(crown, ext(seat2d, CROWN_BOT-0.2, LID_T+0.15))                                    # 손잡이 플러그 자리
crown = D(crown, taper(seat2d, 0.9, CROWN_BOT-0.1, CROWN_BOT+0.8))                          # ★ 입구 모따기 (베드 쪽 코끼리발 + 안내)
# ── ★ 돔 자리 : 넓은 자리 + 45도 천장 홈 ──
crown = D(crown, cyl(CB_R, 20, (0, 0, SK_BOT+10)))                                          # 돔 치마가 들어오는 자리 (바닥 = 앉는 면)
crown = D(crown, tube_rev([[CB_R-0.01, Z0-0.5], [CB_R+0.6, Z0+0.1], [CB_R-0.01, Z0+0.1]]))  # 자리 입구 모따기
def zc_(r, ax): return SK_BOT + LUG_V + ax + (LUG_R - r)                                    # 45도 천장
def grv(ax): return [(CB_R-0.05, GRV_FL), (GRV_R, GRV_FL), (GRV_R, zc_(GRV_R, ax)), (CB_R-0.05, zc_(CB_R-0.05, ax))]
EW = BAY_W + 2*ENT_MARG
for i in range(BAY_N):
    a0 = 90.0 + 360.0*i/BAY_N; g0 = a0 - BAY_W/2 - STOP_MARG; g1 = a0 + BAY_TURN + EW/2
    crown = D(crown, sweep(g0, g1, lambda t: grv(AX_LOCK + (AX_IN-AX_LOCK)*t), 64))         # 돌아가는 홈 (천장이 끝으로 갈수록 낮다)
    crown = D(crown, arc(a0+BAY_TURN-EW/2, a0+BAY_TURN+EW/2, CB_R-0.05, GRV_R, GRV_FL, Z0+0.5, 32))   # 세로 진입 홈
crown = save(crown, "02_crown_RED")
letters.export(f"{OUT}/02c_letters_BLACK.stl")

# ═══════════════════ 09 십자 (첨탑은 돔과 한 몸) ═══════════════════
arms = []
for dx, dy, L in [(1, 0, CR['lx']), (-1, 0, CR['lx']), (0, 1, CR['up']), (0, -1, CR['dn'])]:
    px, py = -dy, dx
    arms.append(SPoly([(px*CR['a'], py*CR['a']), (dx*L+px*CR['b'], dy*L+py*CR['b']),
                       (dx*L-px*CR['b'], dy*L-py*CR['b']), (-px*CR['a'], -py*CR['a'])]))
cpo = unary_union(arms).buffer(CR['fil'], resolution=16).buffer(-CR['fil'], resolution=16)
cpo = cpo.buffer(0.5, resolution=16).buffer(-0.5, resolution=16)
PEG_TIP = CR['a'] - 0.65
cpo = cpo.union(sbox(-CR['a'], -CR['dn']-CR['peg']+1.0, CR['a'], -CR['dn']+1.0))
cpo = cpo.union(SPoly([(-CR['a'], -CR['dn']-CR['peg']+1.0), (CR['a'], -CR['dn']-CR['peg']+1.0),
                       (PEG_TIP, -CR['dn']-CR['peg']), (-PEG_TIP, -CR['dn']-CR['peg'])]))
cross_flat = ext(cpo, -CR['t']/2, CR['t']/2)
cross_flat = save(cross_flat, "09_cross_YELLOW")
cross = cross_flat.copy(); cross.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [1, 0, 0]))
cross.apply_translation([0, 0, CROSS_Z + CR['dn']]); cross = vz(cross)

# ═══════════════════ 03 보드 받침 (손잡이 돌출부 위에 얹는 판 + 기둥 4개) ═══════════════════
#  정수 실측 (2026-11-14) : 왕관 밑면에서 보드까지의 깊이 — 앞 5.6 · 뒤 8.4 · 좌우 9.5 (각 변 한가운데, 가장자리 2mm).
#  기둥이 그 높이까지 올라가 보드를 왕관 모서리 탭에 눌러 붙인다.
#  ★ 기둥을 딱 맞게 만들면 '왕관이 손잡이에 앉는 면' 과 '보드를 누르는 면' 둘 다 딱딱해져 과구속이 된다 (v20 의 실수).
#    → 2026-11-14 정수 : 스펀지는 뺀다. 기둥이 보드에 직접 닿는다.
#      기둥은 실측보다 SEAT_GAP(0.3) 만 짧다 — 실측끼리 ±0.4 쯤 어긋나므로(9.5 − USB 3.2 = 6.3 인데 5.6 으로 잼),
#      조금이라도 길면 왕관이 손잡이에 끝까지 안 닫힌다. 짧은 쪽은 보드가 0.3 쯤 놀 뿐이다.
#  기둥은 각 변 '한가운데' 에만 선다 → 네 모서리와 그 밖의 패드(전선 납땜 자리)는 전부 비어 있다.
#  손잡이를 다시 뽑지 않아도 되게 별도 부품으로 뺐다. 판은 왕관의 보드 자리(26.2각)가 좌우를 잡는다.
PLUG_TOP_H = 1.8                  # 손잡이 돌출부 윗면 (red_v23.py 의 PLUG_TOP)
SEAT_DEPTH = {'+y': 5.6, '-y': 8.4, '+x': 9.5, '-x': 9.5}       # 왕관 밑면 → 보드 (실측)
SEAT_GAP   = 0.3                  # 직접 닿는다. 안전 쪽으로 0.3 짧게
SEAT_T, SEAT_PL = 2.0, 1.0                    # 기둥 두께(안쪽으로) · 바닥판 두께
SEAT_WD = {'+y': 5.0, '-y': 5.0, '+x': 4.0, '-x': 4.0}        # 기둥 폭 (좌우는 핀 구멍 줄이라 4.0 — 옆 패드의 전선을 피한다)
SP_HW = BOARD_W/2 + 0.07          # 판 반폭 12.7 (보드 자리 13.085 보다 편측 0.38 작다)
seatp = ext(stad(SP_HW*2, SP_HW*2, POK_CR), PLUG_TOP_H+0.02, PLUG_TOP_H+SEAT_PL)
seatp = D(seatp, cyl(8.6, 6, (0, 0, PLUG_TOP_H)))                                           # 가운데 : 전선 · 링 자리
for k, dep in SEAT_DEPTH.items():
    ztop = CROWN_BOT + dep - SEAT_GAP; r1 = BOARD_W/2 - 0.1; r0 = r1 - SEAT_T
    b = box(SEAT_T, SEAT_WD[k], ztop-(PLUG_TOP_H+0.5), ((r0+r1)/2, 0, (ztop+PLUG_TOP_H+0.5)/2))
    seatp = U(seatp, rotz(b, {'+x': 0, '+y': 90, '-x': 180, '-y': 270}[k]))
seatp = D(seatp, rotz(box(1.2, 3.0, 4, (0, 9.6, PLUG_TOP_H+SEAT_PL)), 0))                   # 앞(+y · 5.6 쪽) 표시 홈
seatp = save(seatp, "03_boardseat_RED")

# ═══════════════════ 시험 조각 (이음부만 · 20분) ═══════════════════
t_crown = save(I(crown, tube_rev([[16.2, Z_BTOP+0.4], [HEAD_R+0.5, Z_BTOP+0.4], [HEAD_R+0.5, Z0+1.6], [16.2, Z0+1.6]])), "18_test_crown")
t_dome  = save(I(dome, cyl(30, 6.0, (0, 0, SK_BOT+3.0))), "19_test_dome")

# ═══════════════════ 검증 ═══════════════════
bad = 0
def V(a, b):
    try: return abs(vz(a.intersection(b)).volume)
    except Exception: return float('nan')
def chk(name, v, want_zero=True, note=""):
    global bad
    ok = (v < 0.05) if want_zero else (v > 0.05); bad += (not ok)
    print(f"  {name:38s} {v:8.3f} mm3   {'✔' if ok else '✘'}  {note}")
fat = dome.copy(); fat.apply_scale([1+0.20/LUG_R, 1+0.20/LUG_R, 1.0])                        # 돔이 반경 0.2 뚱뚱하게 나온 경우
print("\n── 검증 1 : 제자리 ──")
chk("돔 ∩ 왕관 (잠긴 자리)", V(dome, crown))
chk("돔(+0.2 뚱뚱) ∩ 왕관", V(fat, crown))
chk("십자 ∩ 돔 (어깨가 구슬에 앉는다)", V(mv(cross, [0, 0, 0.3]), dome))
brd = box(BOARD_W, BOARD_W, BOARD_T, (0, 0, Z_BRD+BOARD_T/2)); chk("보드 ∩ 왕관", V(brd, crown))
hp = "/home/claude/v23/05_handle_RED.stl"
if os.path.exists(hp):
    hand = trimesh.load(hp); hs = max(hand.split(only_watertight=False), key=lambda c: c.volume)
    chk("손잡이(v23) ∩ 왕관", V(hs, crown))
    w = max(V(mv(hs, [0, 0, -d]), crown) for d in (1, 2, 3, 4))
    chk("손잡이 넣는 길", w)
    chk("손잡이 0.6 옆으로 → 자리 벽에", V(mv(hs, [0.6, 0, 0]), crown), False)
chk("보드 받침 ∩ 왕관", V(seatp, crown))
if os.path.exists(hp): chk("보드 받침 ∩ 손잡이", V(seatp, hs))
chk("보드 받침 넣는 길", max(V(mv(seatp, [0, 0, -d]), crown) for d in (1, 2, 3, 4, 5)))
chk("보드 받침 0.6 옆으로 → 보드 자리 벽에", V(mv(seatp, [0.6, 0, 0]), crown), False)
print("\n── 검증 2 : 넣는 길 · 돌리는 길 ──")
w = max(V(mv(rotz(dome, BAY_TURN), [0, 0, d]), crown) for d in (0.05, 0.5, 1, 1.5, 2, 2.5, 3, 4))
chk("위에서 내려 넣기 (8 높이)", w)
w = max(V(mv(rotz(dome, BAY_TURN+s), [0, 0, d]), crown) for s in (-2.5, 2.5) for d in (0.05, 1, 2, 3))
chk("  〃 2.5도 틀어져도", w)
w = max(V(mv(rotz(fat, BAY_TURN), [0, 0, d]), crown) for d in (0.05, 1, 2, 3))
chk("  〃 돔이 0.2 뚱뚱해도", w)
w = max(V(mv(rotz(dome, BAY_TURN), [dx, dy, d]), crown) for dx, dy in ((0.4, 0), (0, 0.4), (-0.3, -0.3)) for d in (0.05, 1, 2, 3))
chk("  〃 0.4 옆으로 치우쳐도", w)
w = max(V(rotz(dome, a), crown) for a in np.arange(BAY_TURN, -0.01, -2.0))
chk("30도 → 0도 돌리기 (16 각도)", w)
w = max(V(rotz(fat, a), crown) for a in np.arange(BAY_TURN, -0.01, -3.0))
chk("  〃 돔이 0.2 뚱뚱해도", w)
w = max(V(mv(rotz(dome, a), [0, 0, 0.2]), crown) for a in np.arange(BAY_TURN, -0.01, -3.0))
chk("  〃 러그가 0.2 두꺼워도", w)
print("\n── 검증 3 : 걸려야 할 곳 ──")
chk("잠긴 자리에서 위로 당김 → 안 빠짐", V(mv(dome, [0, 0, 0.8]), crown), False)
chk("진입 자리에서 위로 → 빠짐", V(mv(rotz(dome, BAY_TURN), [0, 0, 0.8]), crown))
chk("십자 아래로 → 구슬에 앉음", V(mv(cross, [0, 0, -0.3]), dome), False)
chk("0도 넘어 더 돌림 → 끝벽", V(rotz(dome, -2.0), crown), False)
chk("돔 아래로 → 자리 바닥", V(mv(dome, [0, 0, -0.3]), crown), False)
chk("돔 0.9 옆으로 → 자리 벽", V(mv(dome, [0.9, 0, 0]), crown), False)
chk("보드 위로 → 모서리 탭", V(mv(brd, [0, 0, 0.5]), crown), False)
print("\n── 숫자 ──")
print(f"  돔 치마 Ø{DOME_R0*2:.1f} ↔ 왕관 자리 Ø{CB_R*2:.1f}   반경 틈 {FIT_DOME}")
print(f"  러그 Ø{LUG_R*2:.1f} ↔ 홈 Ø{GRV_R*2:.1f}   반경 틈 {FIT_DOME} · 물림 {LUG_R-CB_R:.2f}")
print(f"  러그 위 틈 : 진입 {AX_LOCK+(AX_IN-AX_LOCK)*(BAY_TURN+BAY_W/2+STOP_MARG)/(BAY_TURN+EW/2+BAY_W/2+STOP_MARG):.2f} → 잠김 {AX_LOCK:.2f}")
print(f"  홈 천장 위 살 : 자리 가장자리 {Z0-zc_(CB_R, AX_IN):.2f} ~ 홈 끝 {Z0-zc_(GRV_R, AX_IN):.2f}mm")
print(f"  진입 홈 {EW:.0f}도 (러그 {BAY_W:.0f}도 + 좌우 {ENT_MARG:.0f}도 = {math.radians(ENT_MARG)*LUG_R:.2f}mm)")
print(f"  손잡이 플러그 28.3 ↔ 자리 {SEAT_HW*2:.1f}   편측 {FIT_SEAT}")
print("  보드 받침 기둥 끝 (왕관 밑면 기준) : " + " · ".join(f"{k} {v-SEAT_GAP:.1f}" for k, v in SEAT_DEPTH.items()) + f"  (실측보다 {SEAT_GAP} 짧다 · 스펀지 없음)")
print(f"  결과 : {'전부 통과' if bad == 0 else str(bad)+' 건 실패'}")

# ═══════════════════ 출력 방향 ═══════════════════
P = "/home/claude/v24_plate"; os.makedirs(P, exist_ok=True)
def plate_(name, m, src=None):
    m = m.copy(); b = m.bounds; sh = [-(b[0][0]+b[1][0])/2, -(b[0][1]+b[1][1])/2, -b[0][2]] if src is None else src
    m.apply_translation(sh); nz = m.face_normals[:, 2]; zc = m.triangles_center[:, 2]
    ov = m.area_faces[(nz < -0.72) & (nz > -0.999) & (zc > 0.3)].sum(); br = m.area_faces[(nz <= -0.999) & (zc > 0.3)].sum()
    m.export(f"{P}/{name}.stl"); e = m.bounds[1]-m.bounds[0]
    print(f"  {name:18s} {e[0]:5.1f} x {e[1]:5.1f} x {e[2]:5.1f}   45도 넘는 면 {ov:6.1f}mm2 · 수평 천장 {br:6.1f}mm2")
    return sh
print("\n── 출력 방향 (전부 세운 그대로) ──")
plate_("01_dome_CLEAR", dome)
sh = plate_("02_crown_RED", crown); plate_("02c_letters_BLACK", letters, sh)                # 글자는 왕관과 같은 자리
plate_("09_cross_YELLOW", cross_flat); plate_("03_boardseat_RED", seatp)
plate_("18_test_crown", t_crown); plate_("19_test_dome", t_dome)
