import trimesh, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
S='/home/claude/v17'
H=trimesh.load(f'{S}/05_handle_RED.stl'); C=trimesh.load(f'{S}/07_carrier_RED.stl')
B=trimesh.load(f'{S}/06_button_RED.stl')
fig,axs=plt.subplots(1,3,figsize=(13.5,5.2))
# (1) x=0 종단면
ax=axs[0]
for m,c in [(H,'#c8102e'),(C,'#7a0a18'),(B,'#e05a6a')]:
    s=m.section(plane_origin=[0,0,0],plane_normal=[1,0,0])
    if s is None: continue
    for e in s.entities:
        v=s.vertices[e.points]; ax.plot(v[:,1],v[:,2],color=c,lw=1.2)
ax.set_aspect('equal'); ax.set_xlim(-12,14); ax.set_ylim(-66,-8); ax.grid(alpha=.3)
ax.set_title('x=0  handle + carrier + button',fontsize=10)
# (2) 버튼 스테이션 단면 z=-22
ax=axs[1]
for m,c in [(H,'#c8102e'),(C,'#7a0a18'),(B,'#e05a6a')]:
    s=m.section(plane_origin=[0,0,-22.0],plane_normal=[0,0,1])
    if s is None: continue
    for e in s.entities:
        v=s.vertices[e.points]; ax.plot(v[:,0],v[:,1],color=c,lw=1.3)
for r in (3.0,3.25): ax.add_patch(plt.Rectangle((-r,5.74-3.7),2*r,3.7,fill=False,ls=':',ec='#333'))
ax.set_aspect('equal'); ax.set_xlim(-11,11); ax.set_ylim(-11,13); ax.grid(alpha=.3)
ax.set_title('z=-22  switch station (dotted = tact 6.0/6.5)',fontsize=10)
# (3) 포트 스테이션 z=-58
ax=axs[2]
for m,c in [(H,'#c8102e'),(C,'#7a0a18')]:
    s=m.section(plane_origin=[0,0,-58.0],plane_normal=[0,0,1])
    if s is None: continue
    for e in s.entities:
        v=s.vertices[e.points]; ax.plot(v[:,0],v[:,1],color=c,lw=1.3)
ax.add_patch(plt.Rectangle((-8.94/2,-2.38+1.0),8.94,3.26,fill=False,ls=':',ec='#333'))
ax.add_patch(plt.Rectangle((-9.6/2,-2.38),9.6,1.0,fill=False,ls=':',ec='#333'))
ax.set_aspect('equal'); ax.set_xlim(-11,11); ax.set_ylim(-11,11); ax.grid(alpha=.3)
ax.set_title('z=-58  port station (dotted = shell + PCB)',fontsize=10)
plt.tight_layout(); plt.savefig('/home/claude/v17_sec.png',dpi=135,facecolor='white')
