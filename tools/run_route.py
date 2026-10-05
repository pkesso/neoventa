import json, time, pickle
from route import route_all, simplify, pos
from render import render
placed = {k: tuple(v) for k, v in json.load(open("placed2.json")).items()}
t=time.time()
R, failed = route_all(placed, verbose=False)
print("failed:", failed, "time", round(time.time()-t,1))
tracks = [(["F.Cu","B.Cu"][L], net, simplify(cells)) for net, segs in R.tracks.items() for (L, cells) in segs]
vias = [(pos(i,j)[0], pos(i,j)[1], net) for net, vs in R.vias.items() for (i,j) in vs]
render(placed, tracks, vias, fn="routed.png", title=f"failed: {failed}")
pickle.dump((placed, tracks, vias, failed), open("routed.pkl","wb"))
print(len(tracks), "segments", len(vias), "vias")
