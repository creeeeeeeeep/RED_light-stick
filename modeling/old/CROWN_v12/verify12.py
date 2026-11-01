import trimesh, itertools, math, numpy as np
D='/home/claude/v12'
def L(n): return trimesh.load(f'{D}/{n}.stl')
BOARD_W,BOARD_T,LID_T,SPR_H,HAND_R,BORE_R,HAND_BOT = 25.0,5.5,2.6,2.2,8.5,6.5,-57.5
Z_BRD = LID_T+SPR_H
P={n:L(n) for n in ['01_dome_WHITE','02_crown_RED','03_lid_RED','04_spring_RED',
                    '05_handle_RED','08_finial_RED','_cross_placed']}
bc=L('06_btncap_RED'); bc.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2,[1,0,0]))
bc.apply_translation([0, HAND_R+2.2-1.5, -18.0]); P['06_btncap_RED']=bc
print('── 덩어리 수 ──')
for n,m in P.items():
    k=len(m.split(only_watertight=False)); print(f'   {n:18s} {k}  {"OK" if k==1 else "⚠"}')
print('── 파트 간 간섭 (조립 위치) ──')
bad=[(a,b,round(P[a].intersection(P[b]).volume,2)) for a,b in itertools.combinations(P,2)
     if P[a].intersection(P[b]).volume>0.6]
for a,b,v in bad:
    print(f'   {a} ↔ {b} : {v} mm3' + ('  ← 스냅 물림(정상)' if 'btncap' in a+b else ''))
if not bad: print('   없음')
print('── 내부 ──')
board=trimesh.creation.box((BOARD_W,BOARD_W,BOARD_T)); board.apply_translation([0,0,Z_BRD+BOARD_T/2])
led=trimesh.creation.box((20.6,20.6,1.6)); led.apply_translation([0,0,Z_BRD+BOARD_T+0.8])
print(f'   보드↔왕관 {P["02_crown_RED"].intersection(board).volume:6.2f} / 보드↔뚜껑 {P["03_lid_RED"].intersection(board).volume:6.2f} / LED침범 {P["02_crown_RED"].intersection(led).volume:6.2f}')
print(f'   스프링이 미는 양 {P["04_spring_RED"].intersection(board).volume:6.2f} mm3')
up=trimesh.creation.box((BOARD_W,BOARD_W,BOARD_T)); up.apply_translation([0,0,Z_BRD+BOARD_T/2+0.5])
print(f'   0.5mm 더 올리면 걸림 {P["02_crown_RED"].intersection(up).volume:6.2f}  (>0)')
print('── 배선 / 커넥터 ──')
w=trimesh.creation.cylinder(radius=2.2,height=200)   # 선다발 Ø4.4
w.apply_translation([0,0,HAND_BOT+100])
print(f'   선다발이 손잡이 구멍 통과 : 손잡이 {P["05_handle_RED"].intersection(w).volume:7.2f} / 뚜껑 {P["03_lid_RED"].intersection(w).volume:6.2f}  (0)')
ring = P['04_spring_RED']
wr = trimesh.creation.box((30,1.4,1.4)); wr.apply_translation([0,10.0,LID_T+SPR_H-0.8])
wr.apply_transform(trimesh.transformations.rotation_matrix(math.pi/4,[0,0,1]))   # 잎을 피해 45도로
print(f'   선이 스프링 위를 지나감(45도) : {ring.intersection(wr).volume:6.2f}  (0)')
fb = trimesh.creation.box((11.0,5.0,14.0)); fb.apply_translation([0,0,HAND_BOT+5.5])
print(f'   암 브레이크아웃이 자리에   : {P["05_handle_RED"].intersection(fb).volume:6.2f}  (0)')
plug = trimesh.creation.box((8.8,3.4,8.0)); plug.apply_translation([0,0,HAND_BOT-3.0])
print(f'   USB 플러그가 구멍으로 들어감: {P["05_handle_RED"].intersection(plug).volume:6.2f}  (0)')
d=P['01_dome_WHITE']
print('   돔이 왕관 안으로 내려감 :', [round(P['02_crown_RED'].intersection((lambda q:(q.apply_translation([0,0,z]),q)[1])(d.copy())).volume,2) for z in (0,3,8,18)])
