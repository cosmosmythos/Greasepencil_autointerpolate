import bisect
import math

import bpy
import numpy as np
from mathutils import Vector

from ..utils.curve_points import find_corners

_MAX_POINTS = 4096
_EVAL_RES = 16


def _get_subdivs() -> int:
    try:
        return int(bpy.context.scene.gp_bezier_resample_subdiv)
    except Exception:
        return 2


def _auto_bezier_enabled() -> bool:
    try:
        addon = bpy.context.preferences.addons.get("bl_ext.user_default.gp_auto_interpolate")
        if addon is not None and not bool(addon.preferences.draw_sensor_enabled):
            return False
    except Exception:
        pass
    try:
        if not bool(bpy.context.scene.gp_bezier_fit_enabled):
            return False
    except Exception:
        return False
    return True


def _eval_bezier(p0, c1, c2, p1, t):
    # cubic B(t)
    u = 1 - t
    return p0 * (u ** 3) + c1 * (3 * u * u * t) + c2 * (3 * u * t * t) + p1 * (t ** 3)


def _evaluated_stroke_data(drawing, stroke, stroke_index):

    try:
        curve_type = 1
        attr = drawing.attributes.get('curve_type')
        if attr is not None and stroke_index < len(attr.data):
            curve_type = int(attr.data[stroke_index].value)
    except Exception:
        curve_type = 1
    n = len(stroke.points)
    if n < 2 or curve_type == 1:  # POLY
        return [p.position.copy() for p in stroke.points], [p.radius for p in stroke.points], [p.opacity for p in stroke.points]

    eval_pos, eval_rad, eval_opa = [], [], []
    for i in range(n - 1):
        p0 = stroke.points[i].position.copy()
        p1 = stroke.points[i + 1].position.copy()
        r0, r1 = stroke.points[i].radius, stroke.points[i + 1].radius
        o0, o1 = stroke.points[i].opacity, stroke.points[i + 1].opacity

        try:
            c1 = stroke.points[i].handle_right.position.copy() if stroke.points[i].handle_right else p0
            c2 = stroke.points[i + 1].handle_left.position.copy() if stroke.points[i + 1].handle_left else p1
        except Exception:
            c1, c2 = p0, p1
        if curve_type == 2:  # BEZIER
            for k in range(_EVAL_RES):
                t = k / _EVAL_RES
                eval_pos.append(_eval_bezier(p0, c1, c2, p1, t))
                eval_rad.append(r0 + t * (r1 - r0))
                eval_opa.append(o0 + t * (o1 - o0))
        else:
            for k in range(_EVAL_RES):
                t = k / _EVAL_RES
                eval_pos.append(p0.lerp(p1, t))
                eval_rad.append(r0 + t * (r1 - r0))
                eval_opa.append(o0 + t * (o1 - o0))
    # last point
    eval_pos.append(stroke.points[-1].position.copy())
    eval_rad.append(stroke.points[-1].radius)
    eval_opa.append(stroke.points[-1].opacity)
    return eval_pos, eval_rad, eval_opa


def _resample_points(positions, radii, opacities, subdivs):
    n = len(positions)
    if subdivs == 0 or n < 2:
        return positions, radii, opacities
    cumul = [0.0]
    total = 0.0
    for i in range(1, n):
        total += (positions[i] - positions[i - 1]).length
        cumul.append(total)
    if total == 0.0:
        return positions, radii, opacities
    avg_edge = total / (n - 1)
    sample_length = avg_edge / subdivs if subdivs != 0 else 0.0
    if sample_length == 0.0:
        count = 1
    else:
        count = int(total / sample_length) + 1
    count = max(2, count)
    count = min(count, _MAX_POINTS)
    new_pos, new_rad, new_opa = [], [], []
    for j in range(count):
        target = total * j / (count - 1) if count > 1 else 0.0
        idx = bisect.bisect_left(cumul, target)
        if idx == 0:
            new_pos.append(positions[0].copy())
            new_rad.append(radii[0])
            new_opa.append(opacities[0])
        elif idx >= n:
            new_pos.append(positions[-1].copy())
            new_rad.append(radii[-1])
            new_opa.append(opacities[-1])
        else:
            prev = cumul[idx - 1]
            seg_len = cumul[idx] - prev
            t = (target - prev) / seg_len if seg_len != 0 else 0.0
            new_pos.append(positions[idx - 1].lerp(positions[idx], t))
            new_rad.append(radii[idx - 1] + t * (radii[idx] - radii[idx - 1]))
            new_opa.append(opacities[idx - 1] + t * (opacities[idx] - opacities[idx - 1]))
    return new_pos, new_rad, new_opa


def _get_error_sq() -> float:
    try:
        err = float(bpy.context.scene.gp_bezier_error)
    except Exception:
        err = 0.02
    return err * err


def _fit_piece(points, max_error=None):
    if max_error is None:
        max_error = _get_error_sq()
    if len(points) < 2:
        return []
    try:
        from .cpp_module import interpolator_module
        import gp_autointerpolate
        mod = interpolator_module if interpolator_module is not None else gp_autointerpolate
    except Exception:
        try:
            import gp_autointerpolate as mod
        except Exception:
            return []
    flat = np.array([c for p in points for c in (p.x, p.y, p.z)], dtype=np.float32)
    try:
        result = mod.fit_bezier_flat(flat, float(max_error))
    except Exception:
        try:
            result = mod.fit_bezier(flat, float(max_error))
            if isinstance(result, list):
                flat_list = []
                for arr in result:
                    flat_list.extend([float(v) for v in arr])
                result = np.array(flat_list, dtype=np.float32)
            else:
                result = np.array(result, dtype=np.float32)
        except Exception:
            return []
    if result is None or len(result) == 0:
        return []
    curves = []
    for i in range(0, len(result), 12):
        if i + 11 >= len(result):
            break
        p0 = Vector((result[i], result[i+1], result[i+2]))
        c1 = Vector((result[i+3], result[i+4], result[i+5]))
        c2 = Vector((result[i+6], result[i+7], result[i+8]))
        p1 = Vector((result[i+9], result[i+10], result[i+11]))
        curves.append((p0, c1, c2, p1))
    return curves


def _curves_to_stroke_data(curves):
    if not curves:
        return None
    positions = []
    handles_left = []
    handles_right = []
    p0, c1, c2, p1 = curves[0]
    positions.append(p0)
    handles_left.append(p0)
    handles_right.append(c1)
    for idx in range(1, len(curves)):
        p0, c1, c2, p1 = curves[idx]
        prev_c2 = curves[idx-1][2]
        positions.append(p0)
        handles_left.append(prev_c2)
        handles_right.append(c1)
    last_p1 = curves[-1][3]
    last_c2 = curves[-1][2]
    if len(curves) == 1:
        positions.append(last_p1)
        handles_left.append(last_c2)
        handles_right.append(last_p1)
    else:
        positions.append(last_p1)
        handles_left.append(last_c2)
        handles_right.append(last_p1)
    return positions, handles_left, handles_right


def _write_bezier_stroke(drawing, last_index, positions, handles_left, handles_right, radii, opacities, is_angle, fuse_indices=None):
    orig_curve_attrs = {}
    try:
        for attr in list(drawing.attributes):
            if attr.domain != 'CURVE' or attr.name in ('position', 'handle_left', 'handle_right', 'handle_type_left', 'handle_type_right'):
                continue
            if last_index < len(attr.data):
                if attr.data_type == 'FLOAT_VECTOR':
                    orig_curve_attrs[attr.name] = attr.data[last_index].vector[:]
                elif attr.data_type in ('FLOAT_COLOR', 'BYTE_COLOR'):
                    try:
                        orig_curve_attrs[attr.name] = attr.data[last_index].color[:]
                    except Exception:
                        orig_curve_attrs[attr.name] = attr.data[last_index].value
                else:
                    orig_curve_attrs[attr.name] = attr.data[last_index].value
    except Exception:
        pass
    try:
        orig_stroke = drawing.strokes[last_index]
        for prop in ('material_index', 'softness', 'cyclic'):
            if hasattr(orig_stroke, prop):
                try:
                    orig_curve_attrs[prop] = getattr(orig_stroke, prop)
                except Exception:
                    pass
    except Exception:
        pass
    try:
        drawing.remove_strokes(indices=(last_index,))
    except Exception:
        return False
    n = len(positions)
    if n < 2:
        return False
    drawing.add_strokes([n])
    new_index = len(drawing.strokes) - 1
    new_stroke = drawing.strokes[new_index]
    for name, value in orig_curve_attrs.items():
        attr = drawing.attributes.get(name)
        if attr is None or new_index >= len(attr.data):
            continue
        try:
            if attr.data_type == 'FLOAT_VECTOR':
                attr.data[new_index].vector = value
            elif attr.data_type in ('FLOAT_COLOR', 'BYTE_COLOR'):
                try:
                    attr.data[new_index].color = value
                except Exception:
                    attr.data[new_index].vector = value
            elif attr.data_type == 'FLOAT2':
                attr.data[new_index].vector = value
            else:
                attr.data[new_index].value = value
        except Exception:
            try:
                setattr(new_stroke, name, value)
            except Exception:
                pass
    for i, point in enumerate(new_stroke.points):
        point.position = positions[i]
        point.radius = radii[i] if i < len(radii) else (radii[-1] if radii else 0.02)
        point.opacity = opacities[i] if i < len(opacities) else (opacities[-1] if opacities else 1.0)
    try:
        for s in drawing.strokes:
            s.select = False
        new_stroke.select = True
        with bpy.context.temp_override(object=bpy.context.active_object, active_object=bpy.context.active_object, selected_objects=[bpy.context.active_object]):
            bpy.ops.grease_pencil.set_curve_type(type='BEZIER', use_handles=False)
    except Exception:
        try:
            curve_type_attr = drawing.attributes.get('curve_type')
            if curve_type_attr is not None and new_index < len(curve_type_attr.data):
                curve_type_attr.data[new_index].value = 2
        except Exception:
            pass
    for name in ('handle_left', 'handle_right'):
        if not drawing.attributes.get(name):
            try:
                drawing.attributes.new(name=name, type='FLOAT_VECTOR', domain='POINT')
            except Exception:
                pass
    for i, point in enumerate(new_stroke.points):
        try:
            if point.handle_left is not None:
                point.handle_left.position = handles_left[i]
            if point.handle_right is not None:
                point.handle_right.position = handles_right[i]
        except Exception:
            pass
    for name in ('handle_type_left', 'handle_type_right'):
        if not drawing.attributes.get(name):
            try:
                drawing.attributes.new(name=name, type='INT', domain='POINT')
            except Exception:
                pass
    try:
        total_points = sum(len(s.points) for s in drawing.strokes)
        offset = total_points - n

        fuse_set = set(fuse_indices) if fuse_indices else set()
        for attr_name in ('handle_type_left', 'handle_type_right'):
            attr = drawing.attributes.get(attr_name)
            if attr is None:
                continue
            flat = [0] * total_points
            try:
                attr.data.foreach_get('value', flat)
            except Exception:
                pass
            for i in range(n):
                flat[offset + i] = 0 if (is_angle and i in fuse_set) else 3
            attr.data.foreach_set('value', flat)
    except Exception:
        pass
    if is_angle and fuse_indices:

        pass
    else:
        try:
            with bpy.context.temp_override(object=bpy.context.active_object, active_object=bpy.context.active_object, selected_objects=[bpy.context.active_object]):
                bpy.ops.grease_pencil.set_handle_type(type='FREE_ALIGN' if is_angle else 'ALIGN')
        except Exception:
            pass
    try:
        drawing.tag_positions_changed()
    except Exception:
        pass
    return True


def _bezier_fit_last_stroke():
    try:
        if not _auto_bezier_enabled():
            return None
        obj = bpy.context.active_object
        if not obj or obj.type != "GREASEPENCIL":
            return None
        scene = bpy.context.scene
        layer = getattr(obj.data.layers, "active", None)
        if layer is None:
            return None
        frame_number = scene.frame_current if scene else None
        drawing = None
        if frame_number is not None:
            for frame in layer.frames:
                if frame.frame_number == frame_number:
                    drawing = frame.drawing
                    break
        if drawing is None or len(drawing.strokes) == 0:
            return None
        last_index = len(drawing.strokes) - 1
        stroke = drawing.strokes[last_index]
        n = len(stroke.points)
        if n < 2:
            return None

        try:
            cttr = drawing.attributes.get('curve_type')
            is_poly = True
            if cttr is not None and last_index < len(cttr.data):
                is_poly = int(cttr.data[last_index].value) == 1
            else:
                is_poly = getattr(stroke, 'curve_type', 1) == 1
        except Exception:
            is_poly = True
        if not is_poly:
            positions, radii, opacities = _evaluated_stroke_data(drawing, stroke, last_index)
        else:
            positions = [p.position.copy() for p in stroke.points]
            radii = [p.radius for p in stroke.points]
            opacities = [p.opacity for p in stroke.points]
            res = _resample_points(positions, radii, opacities, _get_subdivs())
            if res is None:
                return None
            positions, radii, opacities = res

        method = getattr(scene, "gp_bezier_fit_method", "ANGLE")
        if method == 'ANGLE':
            span = int(getattr(scene, "gp_bezier_span", 3))
            angle_raw = float(getattr(scene, "gp_bezier_angle", 0.174533))
            angle = angle_raw if angle_raw > 3.14159 else math.degrees(angle_raw)
            corners = find_corners(positions, span=span, angle=angle)
            if not corners:
                pieces = [positions]
                piece_radii = [radii]
                piece_opac = [opacities]
            else:
                indices = sorted(set(corners))
                pieces, pr, po = [], [], []
                start = 0
                for c in indices:
                    pieces.append(positions[start:c+1])
                    pr.append(radii[start:c+1])
                    po.append(opacities[start:c+1])
                    start = c
                pieces.append(positions[start:])
                pr.append(radii[start:])
                po.append(opacities[start:])
                filtered = [(p, r, o) for p, r, o in zip(pieces, pr, po) if len(p) >= 2]
                if filtered:
                    pieces, pr, po = zip(*filtered)
                    pieces, pr, po = list(pieces), list(pr), list(po)
                else:
                    pieces = [positions]
                    pr = [radii]
                    po = [opacities]
            all_positions, all_hl, all_hr, all_radii, all_opac = [], [], [], [], []
            fuse_indices = []
            for piece, pradii, popac in zip(pieces, pr, po):
                curves = _fit_piece(piece)
                if not curves:
                    continue
                conv = _curves_to_stroke_data(curves)
                if conv is None:
                    continue
                pos, hl, hr = conv
                if all_positions:
                    fuse_indices.append(len(all_positions) - 1)
                    all_hr[-1] = hr[0]
                    pos, hl, hr = pos[1:], hl[1:], hr[1:]
                    pradii = pradii[1:] if len(pradii) > len(pos) else pradii
                    popac = popac[1:] if len(popac) > len(pos) else popac
                if len(pos) != len(pradii):
                    pradii = [pradii[0]] * len(pos) if pradii else [0.02]*len(pos)
                    popac = [popac[0]] * len(pos) if popac else [1.0]*len(pos)
                all_positions.extend(pos)
                all_hl.extend(hl)
                all_hr.extend(hr)
                all_radii.extend(pradii[:len(pos)])
                all_opac.extend(popac[:len(pos)])
            if not all_positions:
                return None
            _write_bezier_stroke(drawing, last_index, all_positions, all_hl, all_hr, all_radii, all_opac, is_angle=True, fuse_indices=fuse_indices)
        else:
            curves = _fit_piece(positions)
            if not curves:
                return None
            pos, hl, hr = _curves_to_stroke_data(curves)
            if pos is None:
                return None
            if len(pos) != len(radii):
                radii = [radii[0]] * len(pos)
                opacities = [opacities[0]] * len(pos)
            _write_bezier_stroke(drawing, last_index, pos, hl, hr, radii, opacities, is_angle=False)
        return None
    except Exception:
        return None
    finally:
        try:
            from . import draw_sensor
            draw_sensor._last_stable = draw_sensor._get_total_counts()
            draw_sensor._has_pending = False
        except Exception:
            pass


def _on_drawing_done():
    try:
        bpy.app.timers.register(_bezier_fit_last_stroke, first_interval=0.0)
    except Exception:
        _bezier_fit_last_stroke()


def register():
    from .draw_sensor import register_drawing_done_callback
    register_drawing_done_callback(_on_drawing_done)


def unregister():
    try:
        from .draw_sensor import unregister_drawing_done_callback
        unregister_drawing_done_callback(_on_drawing_done)
    except Exception:
        pass
