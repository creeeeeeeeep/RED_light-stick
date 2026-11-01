import trimesh, itertools, math, numpy as np
from shapely.geometry import box as sbox
D='/home/claude/v20'
def L(n): return trimesh.load(f'{D}/{n}.stl')
def R(a,ax): return trimesh.transformations.rotation_matrix(a,ax)
def bx(w,d,h,p=(0,0,0)):
    b=trimesh.creation.box((w,d,h)); b.apply_translation(p); return b
BOARD_W,BOARD_T,LID_T,PAD_H,CLAMP = 25.0,5.5,2.6,1.6,0.30
TAB_T,LIP_D = 1.6,2.6
BAND_H = LID_T+PAD_H+BOARD_T+TAB_T+LIP_D
Z_BRD = LID_T+PAD_H; Z_BTOP = Z_BRD+BOARD_T
HAND_R,BORE_R,HAND_BOT,BOT_WALL,BOT_SINK = 8.5,7.0,-63.0,1.4,1.4
CROWN_BOT=-1.0; FLANGE_T=2.6; FLG_BOT=CROWN_BOT-FLANGE_T
TH_ROOT,TH_CREST,TH_P,TH_LEN = 8.2,9.6,2.5,7.0
SK_SW,SK_SH,SK_SL,SK_PW,SK_PT,SK_PL = 8.94,3.26,7.40,9.60,1.00,12.50
PLUG_W,PLUG_H = 8.34,2.56
SW_Z,SW_W,SW_DEEP,SW_LEGS,SW_LEGL,SW_STEM_D,SW_STEM_H = -22.0,6.0,3.6,7.9,1.4,3.5,1.4  # 데이터시트
FIT_SLIDE=0.35; LIGHT_R=15.5
BAY_N,BAY_W,BAY_OUT,BAY_T,BAY_TURN = 3,26.0,1.3,1.2,22.0
CR_R=BORE_R-FIT_SLIDE; CR_BOT=HAND_BOT+BOT_WALL
SWF_Y=min(math.sqrt(CR_R**2-(SW_W/2+FIT_SLIDE)**2), BORE_R-SW_STEM_H-0.40)
STEM_TOP=SWF_Y+SW_STEM_H; BTN_GAP=0.35

N=['01_dome_WHITE','02_crown_RED','03_base_RED','05_handle_RED','07_carrier_RED',
   '08_finial_RED','_cross_placed']
P={n:L(n) for n in N}
EXP={'05_handle_RED':2}          # 손잡이는 '손잡이 + 갇힌 버튼' 2덩어리가 정상
print('── 덩어리 수 ──')
for n,m in P.items():
    k=len(m.split(only_watertight=False)); e=EXP.get(n,1)
    tag='OK' if k==e else '⚠ 분리 출력!'
    if n=='05_handle_RED' and k==e: tag='OK  ← 버튼이 안 붙어 있다는 뜻 (정상)'
    print(f'   {n:18s} {k}  {tag}')
# 손잡이를 손잡이/버튼으로 분리
_hp=sorted(P['05_handle_RED'].split(only_watertight=False), key=lambda m:m.volume)
BTN=_hp[0]; HAND1=_hp[-1]

print('── 파트 간 간섭 (조립 위치) ──')
for a,b in itertools.combinations(P,2):
    v=P[a].intersection(P[b]).volume
    if v>0.6:
        t='  ← 버튼 걸림턱 (정상)' if 'button' in a+b else ''
        print(f'   {a} ↔ {b} : {v:.2f} mm3{t}')

print('── ★ 클램프 (M2 나사 2개) ──')
C,B,H = P['02_crown_RED'],P['03_base_RED'],P['05_handle_RED']
SCR_R,SCR_PILOT,SCR_DEEP,SCR_CLR = 15.8,1.7,6.0,2.5
print(f'   너트 ↔ 왕관 (자리에 앉음)     : {C.intersection(B).volume:7.2f}  (0)')
sc=[]
for sg in (1,-1):
    m2=trimesh.creation.cylinder(radius=1.0,height=SCR_DEEP+FLANGE_T)
    m2.apply_translation([sg*SCR_R,0,CROWN_BOT+SCR_DEEP/2-FLANGE_T/2]); sc.append(m2)
sc=trimesh.util.concatenate(sc)
print(f'   M2 가 왕관 하부구멍에 물림     : {C.intersection(sc).volume:7.2f}  (>0 = 셀프탭)')
print(f'   M2 가 너트 통과구멍을 지나감   : {B.intersection(sc).volume:7.2f}  (0)')

print('── ★ 손잡이 베이어닛 ──')
def hand_at(turn,dz=0.0):
    q=H.copy(); q.apply_transform(R(math.radians(turn),[0,0,1])); q.apply_translation([0,0,dz]); return q
print('   진입 각도(0도)로 밀어 올림    :', [round(B.intersection(hand_at(0,-z)).volume,2) for z in (6,3,0)], '(0)')
print('   진입 → -25도 로 돌리는 중     :', [round(B.intersection(hand_at(a)).volume,2) for a in (-5,-13,-21)], '(0)')
print(f'   잠금 위치 (-25도)             : {B.intersection(hand_at(-25)).volume:7.2f}  (디텐트만)')
print('   잠긴 뒤 아래로 빼려 하면      :', [round(B.intersection(hand_at(-25,-z)).volume,2) for z in (0.3,0.6,1.0)], '(>0 = 걸림)')
print(f'   엉뚱한 각도(+40도)로는 안 들어감: {B.intersection(hand_at(40,-1.0)).volume:7.2f}  (>0)')

print('── ★ 보드 고정 (스프링 폐지) ──')
bd=bx(BOARD_W,BOARD_W,BOARD_T,(0,0,Z_BRD+BOARD_T/2))
print(f'   너트 패드가 보드를 누르는 양   : {B.intersection(bd).volume:7.2f} mm3  (>0 = 크러시 리브가 물림)')
print(f'   보드 ↔ 왕관                   : {C.intersection(bd).volume:7.2f}  (0)')
led=bx(20.6,20.6,1.6,(0,0,Z_BTOP+0.8))
print(f'   LED 영역 침범                 : {C.intersection(led).volume:7.2f}  (0)')
up=bx(BOARD_W,BOARD_W,BOARD_T,(0,0,Z_BRD+BOARD_T/2+0.5))
print(f'   보드를 0.5 더 올리면 걸림탭이  : {C.intersection(up).volume:7.2f}  (>0)')

print('── ★ 돔 베이어닛 ──')
DM=P['01_dome_WHITE']
def dome_at(turn_deg, dz=0.0):
    q=DM.copy(); q.apply_transform(R(math.radians(turn_deg),[0,0,1])); q.apply_translation([0,0,dz]); return q
print(f'   잠금 위치 (0도)               : {C.intersection(dome_at(0)).volume:7.2f}  (디텐트만)')
print(f'   진입 각도 (+22도) 로 내림     :', [round(C.intersection(dome_at(BAY_TURN,z)).volume,2) for z in (14,8,3,0)])
print(f'   진입 각도에서 0도까지 돌리는 중:', [round(C.intersection(dome_at(a)).volume,2) for a in (18,12,6,2)])
print('   잠긴 뒤 위로 뽑으려 하면       :', [round(C.intersection(dome_at(0,z)).volume,2) for z in (0.2,0.4,0.7)], ' (>0 = 러그가 걸림)')
print(f'   엉뚱한 각도(+45도)로는 안 들어감: {C.intersection(dome_at(45,2.0)).volume:7.2f}  (>0)')

print('── ★ 갇힌 버튼 (프린트인플레이스) ──')
import gc
_crop=trimesh.creation.box(extents=[30,40,30]); _crop.apply_translation([0,4.0,SW_Z])
LOC=trimesh.boolean.intersection([HAND1,_crop]); gc.collect()
d=-trimesh.proximity.ProximityQuery(LOC).signed_distance(BTN.sample(4000))
print(f'   버튼 부피                      : {BTN.volume:7.2f} mm3')
print(f'   버튼↔손잡이 최소 인쇄틈        : {d.min():7.3f} mm   (0.30 미만 = 융착 위험)')
def bmv(dy):
    q=BTN.copy(); q.apply_translation([0,dy,0]); return trimesh.boolean.intersection([q,LOC]).volume
print('   밖으로 빼려 하면 (0.35→1.5)    :', [round(bmv(t),2) for t in (0.35,0.6,0.8,1.2,1.5)],
      ' ← 0 이 아니면 못 빠진다')
print('   안으로 누르면 (0.35→1.1)       :', [round(bmv(-t),2) for t in (0.35,0.5,0.7,1.1)],
      ' ← 앞쪽 0 = 눌리는 구간')
stem=trimesh.creation.cylinder(radius=SW_STEM_D/2,height=SW_STEM_H)
stem.apply_transform(R(math.pi/2,[1,0,0])); stem.apply_translation([0,SWF_Y+SW_STEM_H/2,SW_Z])
brest=BTN.copy(); brest.apply_translation([0,BTN_GAP,0])          # 스위치가 밀어낸 '쉬는 위치'
print(f'   쉬는 위치에서 스템에 닿나      : {brest.intersection(stem).volume:7.3f} mm3  (0 근처 = 딱 닿음)')
bp=brest.copy(); bp.apply_translation([0,-0.25,0])                # 데이터시트 행정 0.25
print(f'   0.25mm 눌러 스템을 밀는 양     : {bp.intersection(stem).volume:7.2f} mm3  (>0 = 클릭)')

print('── 캐리어 / 커넥터 / 배선 ──')
CA=P['07_carrier_RED']
for dz in (0,14,30):
    q=CA.copy(); q.apply_translation([0,0,dz])
    print(f'   캐리어 {dz:2d}mm 위에서 손잡이와  : {H.intersection(q).volume:7.2f}  (0)')
pp=sbox(-PLUG_W/2,-PLUG_H/2,PLUG_W/2,PLUG_H/2).buffer(-PLUG_H/2+0.02,resolution=24).buffer(PLUG_H/2-0.02,resolution=24)
MOUTH_Y=-(SK_SH+SK_PT+0.5)/2+SK_PT+SK_SH/2
plug2=trimesh.creation.extrude_polygon(pp,12.0); plug2.apply_translation([0,MOUTH_Y,CR_BOT+6.5-12.0])
print(f'   USB 플러그가 밖에서 커넥터까지 : 손잡이 {H.intersection(plug2).volume:6.2f} / 캐리어 {CA.intersection(plug2).volume:6.2f}')
w=trimesh.creation.cylinder(radius=1.8,height=30); w.apply_translation([0,0,-14])
print(f'   선다발 Ø3.6 가 너트 나사 안으로: {B.intersection(w).volume:7.2f}  (0)')

