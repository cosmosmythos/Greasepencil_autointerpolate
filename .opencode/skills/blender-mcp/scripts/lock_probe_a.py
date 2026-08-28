"""Probe A: engine-only format render — does perlin Mono/UV/RGBA differ?"""
code = r"""
import numpy as np
import texturesynth_core as tsc
from bl_ext.user_default.texturesynth.core.cpp_module import get_engine

e = get_engine()
e.set_resolution(64, 64)

def render(fmt):
    g = tsc.Graph()
    perlin_id = 0x1111
    shuffle_id = 0x2222
    g.add_node(perlin_id, "perlin", fmt, "P")
    g.add_node(shuffle_id, "shuffle", tsc.ChannelFormat.RGBA, "S")
    g.add_connection(perlin_id, 0, shuffle_id, 0)
    g.set_output(shuffle_id)
    gen = e.set_graph(g)
    for _ in range(200):
        e.poll_pending_compiles()
        if e.is_generation_ready(gen):
            break
    e.update_node_params_by_id(perlin_id, [8.0, 5.0, 2.0, 0.5, 0.0, 0.0])
    e.update_node_params_by_id(shuffle_id, [0.0, 1.0, 2.0, 3.0])
    img = e.readback_sync()
    px = np.asarray(img, dtype=np.float32).reshape(-1, 4)
    means = [round(float(px[..., c].mean()), 5) for c in range(4)]
    return means, hashlib_md5(px)
import hashlib
def hashlib_md5(px):
    return hashlib.md5(np.ascontiguousarray(px).tobytes()).hexdigest()[:12]

out = {}
for fmt_name, fmt in [("MONO", tsc.ChannelFormat.Mono),
                      ("UV", tsc.ChannelFormat.UV),
                      ("RGBA", tsc.ChannelFormat.RGBA)]:
    means, h = render(fmt)
    out[fmt_name] = {"means": means, "hash": h}

result = {"formats": out}
"""
from mcp_fetch import send
import json
resp = send(code)
print(json.dumps(resp, indent=1)[:3000])
