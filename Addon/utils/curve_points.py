import math


_GAP = 1


def find_corners(points, span=3, angle=10.0):
    n = len(points)
    if n < 2 * span + 1:
        return []

    angles = []
    for i in range(span, n - span):
        ab = points[i] - points[i - span]
        bc = points[i + span] - points[i]
        la, lb = ab.length, bc.length
        if la < 1e-9 or lb < 1e-9:
            continue
        dot = max(-1.0, min(1.0, ab.normalized().dot(bc.normalized())))
        angles.append((i, math.degrees(math.acos(dot))))

    candidates = [(i, a) for i, a in angles if a >= angle]
    if not candidates:
        return []

    groups = [[candidates[0]]]
    for idx, ang in candidates[1:]:
        if idx - groups[-1][-1][0] <= _GAP:
            groups[-1].append((idx, ang))
        else:
            groups.append([(idx, ang)])

    return [max(g, key=lambda x: x[1])[0] for g in groups]
