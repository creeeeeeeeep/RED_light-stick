import trimesh, itertools, math, numpy as np
from shapely.geometry import box as sbox
D='/home/claude/v18'
def L(n): return trimesh.load(f'{D}/{n}.stl')
def R(a,ax): return trimesh.transformations.rotation_matrix(a,ax)
def bx(w,d,h,p=(0,0,0)):
    b=trimesh.creation.box((w,d,h)); b.apply_translation(p); return b
BOARD_W,BOARD_T,LID_T,SPR_H = 25.0,5.5,2.6,3.2
HAND_R,BORE_R,HAND_BOT,BOT_WALL,BOT_SINK = 8.5,7.0,-63.0,1.4,1.4
SKIRT_R=19.5
Z_BRD = LID_T+SPR_H
SK_SW,SK_SH,SK_SL,SK_PW,SK_PT,SK_PL = 8.94,3.26,7.40,9.60,1.00,12.50
PLUG_W,PLUG_H = 8.34,2.56
SW_Z,SW_W,SW_DEEP,SW_LEGS,SW_LEGL = -22.0,6.0,3.7,6.5,1.4
PAD_UP,LIDW,LIDT,FIT_SLIDE = 2.5,10.6,1.6,0.35
CR_R = BORE_R-FIT_SLIDE; CR_BOT = HAND_BOT+BOT_WALL
POC_H = SK_SH+SK_PT+0.5; MOUTH_Y = -POC_H/2+SK_PT+SK_SH/2
SWF_Y = math.sqrt(CR_R**2-(SW_W/2+FIT_SLIDE)**2); STEM_TOP = SWF_Y+1.2
BZ_FLOOR = HAND_R+PAD_UP-LIDT

N=['01_dome_WHITE','02_crown_RED','03_lid_RED','04_spring_RED','05_handle_RED',
   '07_carrier_RED','08_finial_RED','_cross_placed','06_button_RED']
P={n:L(n) for n in N}
print('── 덩어리 수 ──')
for n,m in P.items():
    k=len(m.split(only_watertight=False)); print(f'   {n:18s} {k}  {"OK" if k==1 else "⚠ 분리 출력!"}')
print('── 파트 간 간섭 (조립 위치) ──')
bad=[(a,b,round(P[a].intersection(P[b]).volume,2)) for a,b in itertools.combinations(P,2)
     if P[a].intersection(P[b]).volume>0.6]
for a,b,v in bad:
    t=''
    if 'dome' in a+b and 'crown' in a+b: t='  ← 돔 크러시 리브 (정상)'
    if 'lid' in a+b and 'crown' in a+b:  t='  ← 뚜껑 스냅 (정상)'
    if 'button' in a+b: t='  ← 버튼 걸림턱 (정상)'
    print(f'   {a} ↔ {b} : {v} mm3{t}')
if not bad: print('   없음')

print('── 내부 (헤드) ──')
board=bx(BOARD_W,BOARD_W,BOARD_T,(0,0,Z_BRD+BOARD_T/2))
led=bx(20.6,20.6,1.6,(0,0,Z_BRD+BOARD_T+0.8))
print(f'   보드↔왕관 {P["02_crown_RED"].intersection(board).volume:6.2f} / 보드↔뚜껑 {P["03_lid_RED"].intersection(board).volume:6.2f} / LED침범 {P["02_crown_RED"].intersection(led).volume:6.2f}')
print(f'   스프링이 미는 양 {P["04_spring_RED"].intersection(board).volume:6.2f}')

print('── ★ 캐리어가 구멍을 통과하나 (위에서 아래로) ──')
H=P['05_handle_RED']; C=P['07_carrier_RED']
for dz in (0, 6, 14, 26, 40):
    q=C.copy(); q.apply_translation([0,0,dz])
    print(f'   {dz:3d}mm 위 지점에서 손잡이와 간섭 : {H.intersection(q).volume:7.2f}  (0)')
print('── 캐리어 최종 위치 ──')
print(f'   캐리어 ↔ 손잡이                 : {H.intersection(C).volume:7.2f}  (0)')
for a in (30,90,180):
    cq=C.copy(); cq.apply_transform(R(math.radians(a),[0,0,1]))
    print(f'   캐리어 {a:3d}도 돌리면 걸림        : {H.intersection(cq).volume:7.2f}  (>0 = 방향키 작동)')

print('── 커넥터 / 플러그 ──')
sk=bx(SK_PW,SK_SH+SK_PT,SK_SL,(0,0,CR_BOT+SK_SL/2))
print(f'   커넥터 몸통이 캐리어 자리에      : {C.intersection(sk).volume:7.2f}  (0)')
tail=bx(SK_PW,SK_PT,SK_PL-SK_SL,(0,-POC_H/2+SK_PT/2,CR_BOT+SK_SL+(SK_PL-SK_SL)/2))
print(f'   PCB 꼬리가 캐리어 슬롯에         : {C.intersection(tail).volume:7.2f}  (0)')
pp=sbox(-PLUG_W/2,-PLUG_H/2,PLUG_W/2,PLUG_H/2).buffer(-PLUG_H/2+0.02,resolution=24).buffer(PLUG_H/2-0.02,resolution=24)
PLUG_IN = 6.5   # 플러그가 리셉터클 안으로 들어가는 깊이
plug=trimesh.creation.extrude_polygon(pp,12.0); plug.apply_translation([0,MOUTH_Y,CR_BOT+PLUG_IN-12.0])
print(f'   ★ USB 플러그가 밖에서 커넥터까지 : 손잡이 {H.intersection(plug).volume:6.2f} / 캐리어 {C.intersection(plug).volume:6.2f}  (0)')

print('── 택트 스위치 ──')
body=bx(SW_W,SW_DEEP,SW_W,(0,SWF_Y-SW_DEEP/2,SW_Z))
print(f'   몸통이 캐리어 자리에             : {C.intersection(body).volume:7.2f}  (크러시 리브만)')
legs=[]
for sg in (1,-1):
    for p in (1,-1):
        legs.append(bx(0.5,SW_DEEP*0.5+SW_LEGL,0.9,
                       [sg*(SW_LEGS/2-0.25), SWF_Y-SW_DEEP-SW_LEGL+(SW_DEEP*0.5+SW_LEGL)/2, SW_Z+p*2.25]))
lg=trimesh.util.concatenate(legs)
print(f'   다리 4개(폭 {SW_LEGS}) 가 자리에    : {C.intersection(lg).volume:7.2f}  (0)')
print(f'   몸통 뒷면을 받쳐주나 (0.5 더 밀면): {C.intersection(bx(SW_W,SW_DEEP,SW_W,(0,SWF_Y-SW_DEEP/2-0.5,SW_Z))).volume:7.2f}  (>0)')
stem=trimesh.creation.cylinder(radius=1.75,height=1.2)
stem.apply_transform(R(math.pi/2,[1,0,0])); stem.apply_translation([0,SWF_Y+0.6,SW_Z])
print(f'   스템이 벽 관통구를 통과          : 손잡이 {H.intersection(stem).volume:6.2f} / 캐리어 {C.intersection(stem).volume:6.2f}  (0)')
B=P['06_button_RED']
print(f'   버튼 플런저가 스템까지 닿나      : 스템과 {B.intersection(stem).volume:6.2f} (0=0.15 틈)')
Bp=B.copy(); Bp.apply_translation([0,-0.40,0])
print(f'   0.40mm 눌렀을 때 스템을 밀음     : {Bp.intersection(stem).volume:7.2f}  (>0)')

print('── 배선 ──')
for nm,yy,zz,hh in [('포트 꼬리부', -0.98, CR_BOT+SK_SL+6.0, 12.0),
                    ('C자 척추',    -2.0,  (CR_BOT+SK_SL+SW_Z)/2, 24.0),
                    ('스위치 스테이션', -2.46, SW_Z, 14.0)]:
    w=trimesh.creation.cylinder(radius=1.3,height=hh); w.apply_translation([0,yy,zz])
    print(f'   선다발 Ø2.6 {nm:12s} 통과     : 캐리어 {C.intersection(w).volume:6.2f} / 손잡이 {H.intersection(w).volume:6.2f}  (0)')
w2=trimesh.creation.cylinder(radius=2.2,height=40); w2.apply_translation([0,0,-6.0])
print(f'   선다발 Ø4.4 가 뚜껑 통과         : {P["03_lid_RED"].intersection(w2).volume:6.2f}  (0)')

print('── 스프링 ──')
SP=P['04_spring_RED']; LD=P['03_lid_RED']
bd0=trimesh.creation.box((BOARD_W,BOARD_W,BOARD_T)); bd0.apply_translation([0,0,Z_BRD+BOARD_T/2])
print(f'   스프링이 보드를 미는 양          : {SP.intersection(bd0).volume:7.2f} mm3  (>0)')
print(f'   스프링 ↔ 뚜껑 (안 눌린 상태)     : {SP.intersection(LD).volume:7.2f}  (0)')
inner=SP.intersection(trimesh.creation.cylinder(radius=10.4,height=20).apply_translation([0,0,LID_T+5]) or 0)
inner.apply_translation([0,0,-0.7])
print(f'   팔만 0.7mm 눌렸을 때 뚜껑에 닿나 : {inner.intersection(LD).volume:7.2f}  (0 = 릴리프 충분)')
nz=SP.face_normals[:,2]<-0.3; zc=SP.triangles_center[:,2]-SP.bounds[0][2]
print(f'   아래 보는 면이 바닥 위에 있는 넓이: {SP.area_faces[nz&(zc>0.15)].sum():7.2f} mm2  (0 = 서포트 불필요)')
import shapely.geometry as _g
sec=SP.section(plane_origin=[0,0,SP.bounds[0][2]+0.5],plane_normal=[0,0,1])
p2,_=sec.to_2D(); ins=[r for poly in p2.polygons_full for r in poly.interiors]
if ins:
    d=min(_g.Point(0,0).distance(_g.LinearRing(r)) for r in ins)
    print(f'   가운데 배선 구멍                 : Ø{d*2:5.1f} mm  (뚜껑 구멍 Ø13.4)')

print('── ★ 출력성 (왕관) ──')
CR2=P['02_crown_RED']
for z in (-0.8,0.2,2.0,3.0,5.0):
    s=CR2.section(plane_origin=[0,0,z],plane_normal=[0,0,1]); pg,_=s.to_2D()
    a=sum(x.area for x in pg.polygons_full); k=len(pg.polygons_full)
    print(f'   z{z:+5.1f} 단면 {a:7.1f}mm2  섬 {k}  {"OK" if k==1 else "⚠ 조각남!"}')
lidbody=trimesh.creation.extrude_polygon(
    sbox(-14.15,-14.15,14.15,14.15).buffer(-8.0,resolution=24).buffer(8.0,resolution=24), 2.6)
print('   뚜껑 본체가 밑에서 자리까지 :', [round(CR2.intersection(
    (lambda q:(q.apply_translation([0,0,d]),q)[1])(lidbody.copy())).volume,2) for d in (-8,-5,-3,-1.5,0)])
bd=trimesh.creation.box((25.0,25.0,5.5))
print('   보드가 밑에서 자리까지     :', [round(CR2.intersection(
    (lambda q:(q.apply_translation([0,0,d]),q)[1])(bd.copy())).volume,2) for d in (-6,-2,2.0,4.8,7.55)])

print('── 자리잡기 (키) ──')
f=P['08_finial_RED']; dm=P['01_dome_WHITE']
for a in (30,90):
    q=f.copy(); q.apply_transform(R(math.radians(a),[0,0,1]))
    print(f'   피니얼 {a:3d}도 → 축에 걸림       : {q.intersection(dm).volume:7.2f}  (>0)')
kd=dm.copy(); kd.apply_transform(R(math.radians(45),[0,0,1]))
print(f'   돔 45도 → 왕관에 걸림           : {P["02_crown_RED"].intersection(kd).volume:7.2f}  (>0)')

