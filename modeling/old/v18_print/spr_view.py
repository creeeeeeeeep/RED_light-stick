import trimesh, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig,axs=plt.subplots(1,3,figsize=(13.5,4.8))
for ax,(v,t,zoff) in zip(axs,[('v17','v17  ramped leaves 19deg (needs support)',0),
                              ('v18','v18  flat spiral (support-free)',0)]):
    m=trimesh.load(f'/home/claude/{v}/04_spring_RED.stl')
    m.apply_translation([0,0,-m.bounds[0][2]])
    for e in m.section(plane_origin=[0,0,0.3],plane_normal=[0,0,1]).entities:
        pass
    # top view outline
    sec=m.section(plane_origin=[0,0,0.4],plane_normal=[0,0,1])
    for e in sec.entities:
        p=sec.vertices[e.points]; ax.plot(p[:,0],p[:,1],color='#c8102e',lw=1.4)
    ax.set_aspect('equal'); ax.set_xlim(-14,14); ax.set_ylim(-14,14); ax.grid(alpha=.3)
    ax.set_title(t,fontsize=10)
# side sections
ax=axs[2]
for v,c,lb in [('v17','#f0a0ac','v17'),('v18','#c8102e','v18')]:
    m=trimesh.load(f'/home/claude/{v}/04_spring_RED.stl'); m.apply_translation([0,0,-m.bounds[0][2]])
    s=m.section(plane_origin=[0,0,0],plane_normal=[0,1,0])
    if s is None: continue
    for e in s.entities:
        p=s.vertices[e.points]; ax.plot(p[:,0],p[:,2],color=c,lw=1.4)
ax.set_aspect('equal'); ax.set_xlim(-14,14); ax.set_ylim(-0.5,4.5); ax.grid(alpha=.3)
ax.set_title('side section  (pale = v17, solid = v18)',fontsize=10)
plt.tight_layout(); plt.savefig('/home/claude/spring_cmp.png',dpi=140,facecolor='white')
