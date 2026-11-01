import trimesh, math, os
S='/home/claude/v12'; O='/home/claude/v12_print'; os.makedirs(O,exist_ok=True)
for f in os.listdir(O): os.remove(f'{O}/{f}')
def L(n): return trimesh.load(f'{S}/{n}.stl')
def flip(m,ax=[1,0,0]):
    m.apply_transform(trimesh.transformations.rotation_matrix(math.pi,ax,m.centroid)); return m
def drop(m):
    m.apply_translation([-(m.bounds[0][0]+m.bounds[1][0])/2,-(m.bounds[0][1]+m.bounds[1][1])/2,-m.bounds[0][2]]); return m
ORDER=[('01_dome_WHITE',      'WHITE', '개구부를 바닥에. 벽3겹·인필0%',            lambda m:m),
       ('02_crown_RED',       'RED',   '밑면 바닥. 서포트 없음',                    lambda m:m),
       ('03_lid_RED',         'RED',   '그대로. 후크가 위로',                       lambda m:m),
       ('04_spring_RED',      'RED',   '그대로. 잎이 위로. 서포트 없음',            lambda m:m),
       ('05_handle_RED',      'RED',   '스트랩 탭이 바닥. 세로 출력',               lambda m:flip(m)),
       ('06_btncap_RED',      'RED',   '눕혀서',                                    lambda m:m),
       ('08_finial_RED',      'RED',   '다리가 바닥',                               lambda m:flip(m)),
       ('09_cross_RED',       'RED',   '반드시 눕혀서 (층이 팔과 나란하게)',        lambda m:m)]
tot=0
print(f"{'파일':24s}{'색':6s}{'크기(mm)':22s}{'부피':8s}방향")
for n,col,note,fn in ORDER:
    m=drop(fn(L(n))); m.export(f'{O}/{n}.stl')
    e=m.bounds[1]-m.bounds[0]; tot+=m.volume
    print(f'  {n:22s}{col:6s}{e[0]:5.1f} x{e[1]:5.1f} x{e[2]:5.1f}   {m.volume/1000:5.2f}cm3  {note}')
print(f'\n  합계 {tot/1000:.1f} cm3  ≒ {tot/1000*1.24:.0f} g (PLA)')
