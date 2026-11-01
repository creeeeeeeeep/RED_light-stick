import trimesh, math, os
S='/home/claude/v18'; O='/home/claude/v18_print'; os.makedirs(O,exist_ok=True)
for f in os.listdir(O):
    if f.endswith('.stl'): os.remove(f'{O}/{f}')
def L(n): return trimesh.load(f'{S}/{n}.stl')
def rot(m,a,ax): m.apply_transform(trimesh.transformations.rotation_matrix(a,ax,m.centroid)); return m
def drop(m):
    m.apply_translation([-(m.bounds[0][0]+m.bounds[1][0])/2,-(m.bounds[0][1]+m.bounds[1][1])/2,-m.bounds[0][2]]); return m
O_=[('01_dome_WHITE',  'WHITE','개구부를 바닥에. 벽3겹·인필0%',              lambda m:m),
    ('02_crown_RED',   'RED',  '밑면 바닥. 벽 4겹',                         lambda m:m),
    ('03_lid_RED',     'RED',  '그대로. 후크가 위로',                       lambda m:m),
    ('04_spring_RED',  'RED',  '그대로. 기둥이 위로. 완전 평판',            lambda m:m),
    ('05_handle_RED',  'RED',  '바닥(플러그 구멍)이 베드. 세로',            lambda m:m),
    ('06_button_RED',  'RED',  '플런저가 위로. 누르는 면이 베드',           lambda m:rot(m,math.pi/2,[1,0,0])),
    ('07_carrier_RED', 'RED',  '포트 쪽이 베드. 세로. 벽 4겹',              lambda m:m),
    ('08_finial_RED',  'RED',  '평평한 밑면이 바닥. 뒤집지 말 것',          lambda m:m),
    ('09_cross_RED',   'RED',  '반드시 눕혀서',                             lambda m:m),
    ('10_fitgauge_RED','RED',  '★ 이것만 먼저 뽑아 공차 확인',              lambda m:m)]
tot=0
print(f"  {'파일':22s}{'색':6s}{'크기(mm)':24s}{'부피':9s}방향")
for n,c,note,fn in O_:
    m=drop(fn(L(n))); m.export(f'{O}/{n}.stl')
    e=m.bounds[1]-m.bounds[0]
    if n!='10_fitgauge_RED': tot+=m.volume
    print(f'  {n:22s}{c:6s}{e[0]:5.1f} x{e[1]:5.1f} x{e[2]:5.1f}   {m.volume/1000:5.2f}cm3  {note}')
print(f'\n  본체 합계 {tot/1000:.1f} cm3  ≒ {tot/1000*1.24:.0f} g (PLA)')
