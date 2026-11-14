import trimesh, math, os, numpy as np
S='/home/claude/v20'; O='/home/claude/v20_print'; os.makedirs(O,exist_ok=True)
for f in os.listdir(O):
    if f.endswith('.stl'): os.remove(f'{O}/{f}')
def L(n): return trimesh.load(f'{S}/{n}.stl')
def rot(m,a,ax): m.apply_transform(trimesh.transformations.rotation_matrix(a,ax,m.centroid)); return m
def drop(m):
    m.apply_translation([-(m.bounds[0][0]+m.bounds[1][0])/2,-(m.bounds[0][1]+m.bounds[1][1])/2,-m.bounds[0][2]]); return m
ORD=[('10_fitgauge_RED','레드','★ 공차 확인용',                            lambda m:m),
     ('01_dome_WHITE','화이트','개구부 바닥. 벽3겹 인필0%',               lambda m:m),
     ('02_crown_RED','레드','밑면 바닥. 벽4겹 + 브림 5mm',                lambda m:m),
     ('03_base_RED','레드','플랜지가 바닥. 패드가 위로',                   lambda m:m),
     ('05_handle_RED','레드','플러그 구멍이 바닥. 세로',                   lambda m:m),
     ('11_btntest_RED','레드','★ 손잡이 전에 이것부터 (2분)',            lambda m:m),
     ('07_carrier_RED','레드','포트 쪽이 바닥. 벽4겹',                     lambda m:m),
     ('08_finial_RED','레드','평평한 밑면이 바닥. 뒤집지 말 것',           lambda m:m),
     ('09_cross_RED','레드','★ 반드시 눕혀서',                            lambda m:m)]
tot=0
print(f"  {'파일':20s}{'크기(mm)':24s}{'부피':9s}{'서포트 필요면':>13s}  방향")
for n,c,note,fn in ORD:
    m=drop(fn(L(n))); m.export(f'{O}/{n}.stl')
    e=m.bounds[1]-m.bounds[0]
    nz=m.face_normals[:,2]<-0.42; zc=m.triangles_center[:,2]
    ov=m.area_faces[nz&(zc>0.4)].sum()
    if n!='10_fitgauge_RED': tot+=m.volume
    flag=''
    print(f'  {n:20s}{e[0]:5.1f} x{e[1]:5.1f} x{e[2]:5.1f}   {m.volume/1000:5.2f}cm3{ov:11.1f}mm2{flag}  {note}')
print(f'\n  본체 합계 {tot/1000:.1f} cm3  ≒ {tot/1000*1.24:.0f} g (PLA)')
