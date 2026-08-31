#include <algorithm>
#include <cmath>
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/pair.h>
#include <vector>

// FTP-SC stroke matching
#include "stroke_matcher.h"
#include "stroke.h"
#include "bezier_fit.h"

namespace nb = nanobind;

// Shorthand for the 1-D float32 numpy array type used everywhere
using FArr = nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>;

const float EPSILON = 1e-6f;
const float PI = 3.14159265358979323846f;

// ============================================================================
// Math Utilities
// ============================================================================

struct Point3D {
  float x, y, z;
  Point3D() : x(0), y(0), z(0) {}
  Point3D(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}
  Point3D operator+(const Point3D &o) const {
    return Point3D(x + o.x, y + o.y, z + o.z);
  }
  Point3D operator-(const Point3D &o) const {
    return Point3D(x - o.x, y - o.y, z - o.z);
  }
  Point3D operator*(float s) const { return Point3D(x * s, y * s, z * s); }
};

struct Point2D {
  float x, y;
  Point2D() : x(0), y(0) {}
  Point2D(float x_, float y_) : x(x_), y(y_) {}
  Point2D operator+(const Point2D &o) const {
    return Point2D(x + o.x, y + o.y);
  }
  Point2D operator-(const Point2D &o) const {
    return Point2D(x - o.x, y - o.y);
  }
  Point2D operator*(float s) const { return Point2D(x * s, y * s); }
};

float length3d(const Point3D &p) {
  return std::sqrt(p.x * p.x + p.y * p.y + p.z * p.z);
}
float length2d(const Point2D &p) { return std::sqrt(p.x * p.x + p.y * p.y); }

Point3D normalize3d(const Point3D &p) {
  float len = length3d(p);
  return (len < EPSILON) ? Point3D(0, 0, 1) : p * (1.0f / len);
}

Point2D normalize2d(const Point2D &p) {
  float len = length2d(p);
  return (len < EPSILON) ? Point2D(1, 0) : p * (1.0f / len);
}

Point3D cross(const Point3D &a, const Point3D &b) {
  return Point3D(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z,
                 a.x * b.y - a.y * b.x);
}

float dot3d(const Point3D &a, const Point3D &b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

Point3D lerp3d(const Point3D &a, const Point3D &b, float t) {
  return Point3D(a.x * (1 - t) + b.x * t, a.y * (1 - t) + b.y * t,
                 a.z * (1 - t) + b.z * t);
}

Point2D rotate90(const Point2D &p) { return Point2D(-p.y, p.x); }

float angle_diff(float a1, float a2) {
  float diff = a2 - a1;
  while (diff > PI)
    diff -= 2 * PI;
  while (diff < -PI)
    diff += 2 * PI;
  return diff;
}

// ============================================================================
// 3D Plane Projection
// ============================================================================

struct Plane {
  Point3D origin, u_axis, v_axis, normal;
};

Plane create_plane_from_points(const Point3D &p1, const Point3D &p2,
                               const Point3D &hint_normal) {
  Plane plane;
  plane.origin = (p1 + p2) * 0.5f;
  Point3D chord = p2 - p1;
  float chord_len = length3d(chord);

  if (chord_len < EPSILON) {
    plane.u_axis = Point3D(1, 0, 0);
    plane.v_axis = Point3D(0, 1, 0);
    plane.normal = Point3D(0, 0, 1);
    return plane;
  }
  plane.u_axis = chord * (1.0f / chord_len);

  Point3D n = (length3d(hint_normal) < EPSILON) ? Point3D(0, 0, 1)
                                                : normalize3d(hint_normal);
  n = n - plane.u_axis * dot3d(n, plane.u_axis);
  if (length3d(n) < EPSILON) {
    n = (std::abs(plane.u_axis.z) < 0.9f)
            ? cross(plane.u_axis, Point3D(0, 0, 1))
            : cross(plane.u_axis, Point3D(1, 0, 0));
  }
  plane.normal = normalize3d(n);
  plane.v_axis = normalize3d(cross(plane.normal, plane.u_axis));
  return plane;
}

Point2D project_to_plane(const Point3D &p, const Plane &plane) {
  Point3D local = p - plane.origin;
  return Point2D(dot3d(local, plane.u_axis), dot3d(local, plane.v_axis));
}

Point3D unproject_from_plane(const Point2D &p2d, const Plane &plane,
                             float z_offset = 0.0f) {
  return plane.origin + plane.u_axis * p2d.x + plane.v_axis * p2d.y +
         plane.normal * z_offset;
}

// ============================================================================
// Arc Interpolation
// ============================================================================

Point3D bezier_arc_interpolate_3d(const Point3D &start, const Point3D &end,
                                  float t, float arc_amount,
                                  float arc_direction,
                                  const Point3D &plane_normal) {
  if (arc_amount < EPSILON)
    return lerp3d(start, end, t);
  Plane plane = create_plane_from_points(start, end, plane_normal);
  Point2D s2d = project_to_plane(start, plane),
          e2d = project_to_plane(end, plane);
  Point2D mid = (s2d + e2d) * 0.5f, chord = e2d - s2d;
  Point2D perp = rotate90(normalize2d(chord));
  Point2D control =
      mid + perp * (length2d(chord) * arc_amount * arc_direction * 0.5f);
  float t1 = 1.0f - t;
  Point2D result2d = s2d * (t1 * t1) + control * (2 * t1 * t) + e2d * (t * t);
  float z_interp = start.z * (1 - t) + end.z * t;
  return unproject_from_plane(result2d, plane,
                              z_interp - (plane.origin.z +
                                          plane.u_axis.z * result2d.x +
                                          plane.v_axis.z * result2d.y));
}

Point3D spiral_arc_interpolate_3d(const Point3D &start, const Point3D &end,
                                  float t, float arc_amount,
                                  float arc_direction,
                                  const Point3D &plane_normal) {
  if (arc_amount < EPSILON)
    return lerp3d(start, end, t);
  float dist = length3d(end - start);
  if (dist < EPSILON)
    return start;

  Plane plane = create_plane_from_points(start, end, plane_normal);
  Point2D s2d = project_to_plane(start, plane),
          e2d = project_to_plane(end, plane);
  Point2D mid = (s2d + e2d) * 0.5f, chord = e2d - s2d;
  float chord_len = length2d(chord);
  if (chord_len < EPSILON)
    return lerp3d(start, end, t);

  Point2D perp = rotate90(normalize2d(chord));
  Point2D pole = mid + perp * (chord_len * (1.0f / std::max(arc_amount, 0.1f)) *
                               0.5f * arc_direction);
  Point2D s_rel = s2d - pole, e_rel = e2d - pole;
  float r1 = length2d(s_rel), r2 = length2d(e_rel);

  if (r1 < EPSILON || r2 < EPSILON)
    return bezier_arc_interpolate_3d(start, end, t, arc_amount, arc_direction,
                                     plane_normal);

  float theta1 = std::atan2(s_rel.y, s_rel.x),
        theta2 = std::atan2(e_rel.y, e_rel.x);
  float delta_theta = angle_diff(theta1, theta2);
  if (std::abs(delta_theta) < EPSILON)
    return bezier_arc_interpolate_3d(start, end, t, arc_amount, arc_direction,
                                     plane_normal);

  float k = std::log(r2 / r1) / delta_theta;
  if (std::abs(k) > 10.0f)
    return bezier_arc_interpolate_3d(start, end, t, arc_amount, arc_direction,
                                     plane_normal);

  float theta = theta1 + t * delta_theta;
  float r = r1 * std::exp(k * (theta - theta1));
  if (r < EPSILON || r > chord_len * 100.0f)
    return bezier_arc_interpolate_3d(start, end, t, arc_amount, arc_direction,
                                     plane_normal);

  Point2D result2d = pole + Point2D(std::cos(theta), std::sin(theta)) * r;
  float z_interp = start.z * (1 - t) + end.z * t;
  return unproject_from_plane(result2d, plane,
                              z_interp - (plane.origin.z +
                                          plane.u_axis.z * result2d.x +
                                          plane.v_axis.z * result2d.y));
}

// ============================================================================
// Helper: build a numpy array from a std::vector with capsule ownership
// ============================================================================

static nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>
make_array(const std::vector<float> &v) {
  float *buf = new float[v.size()];
  std::copy(v.begin(), v.end(), buf);
  return nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>(
      buf, {(size_t)v.size()},
      nb::capsule(buf, [](void *p) noexcept { delete[] (float *)p; }));
}

// ============================================================================
// Main Interpolator Class
// ============================================================================

class Interpolator {
private:
  bool is_position_data(const float *data, size_t total) {
    if (total == 0 || total < 6 || total % 3 != 0)
      return false;
    bool all_unit = true;
    float min_v = data[0], max_v = data[0];
    for (size_t i = 0; i < total; ++i) {
      if (data[i] < 0.0f || data[i] > 1.0f)
        all_unit = false;
      min_v = std::min(min_v, data[i]);
      max_v = std::max(max_v, data[i]);
    }
    return !(all_unit && (max_v - min_v) < 0.1f && max_v <= 1.0f);
  }

  // Uniform arc-length resampling for position strokes
  std::vector<float> resample_position_stroke(const float *pos_data,
                                              size_t pos_size,
                                              int target_count) {
    size_t orig_count = pos_size / 3;

    if (orig_count < 2 || target_count < 2) {
      return std::vector<float>(pos_data, pos_data + pos_size);
    }

    if ((int)orig_count == target_count) {
      return std::vector<float>(pos_data, pos_data + pos_size);
    }

    // Calculate cumulative arc lengths
    std::vector<float> cumulative(1, 0.0f);
    float total = 0.0f;

    for (size_t i = 1; i < orig_count; ++i) {
      float dx = pos_data[i * 3] - pos_data[(i - 1) * 3];
      float dy = pos_data[i * 3 + 1] - pos_data[(i - 1) * 3 + 1];
      float dz = pos_data[i * 3 + 2] - pos_data[(i - 1) * 3 + 2];
      total += std::sqrt(dx * dx + dy * dy + dz * dz);
      cumulative.push_back(total);
    }

    std::vector<float> result;
    result.reserve(target_count * 3);

    // First point
    result.push_back(pos_data[0]);
    result.push_back(pos_data[1]);
    result.push_back(pos_data[2]);

    // Interior points - uniform arc-length sampling
    for (int i = 1; i < target_count - 1; ++i) {
      float target_len = (total * i) / (target_count - 1);
      size_t seg = 0;
      for (size_t j = 1; j < cumulative.size(); ++j) {
        if (cumulative[j] >= target_len) {
          seg = j - 1;
          break;
        }
      }
      if (seg >= orig_count - 1)
        seg = orig_count - 2;

      float t = (cumulative[seg + 1] - cumulative[seg] > EPSILON)
                    ? (target_len - cumulative[seg]) /
                          (cumulative[seg + 1] - cumulative[seg])
                    : 0.0f;

      result.push_back(pos_data[seg * 3] * (1 - t) + pos_data[(seg + 1) * 3] * t);
      result.push_back(pos_data[seg * 3 + 1] * (1 - t) + pos_data[(seg + 1) * 3 + 1] * t);
      result.push_back(pos_data[seg * 3 + 2] * (1 - t) + pos_data[(seg + 1) * 3 + 2] * t);
    }

    // Last point
    result.push_back(pos_data[(orig_count - 1) * 3]);
    result.push_back(pos_data[(orig_count - 1) * 3 + 1]);
    result.push_back(pos_data[(orig_count - 1) * 3 + 2]);

    return result;
  }

  std::vector<float> resample_scalar(const float *data, size_t data_size,
                                     int target_count) {
    size_t orig = data_size;
    if (orig < 2 || target_count < 2)
      return std::vector<float>(data, data + orig);
    if ((int)orig == target_count)
      return std::vector<float>(data, data + orig);

    std::vector<float> result(target_count);
    for (int i = 0; i < target_count; ++i) {
      float t = (float)i / (float)(target_count - 1);
      float idx = t * (orig - 1);
      int i1 = (int)idx, i2 = std::min(i1 + 1, (int)orig - 1);
      result[i] = data[i1] * (1.0f - (idx - i1)) + data[i2] * (idx - i1);
    }
    return result;
  }

public:
  Interpolator() {}

  float apply_easing(float t, FArr curve) {
    // ndim()==0 means default-constructed FArr (no curve provided).
    // A real easing curve has ndim()==1 with exactly 64 samples.
    if (curve.ndim() == 0 || curve.shape(0) != 64)
      return t;

    if (t <= 0.0f)
      return 0.0f;
    if (t >= 1.0f)
      return 1.0f;

    float idx = t * 63.0f;
    int lo = (int)idx, hi = std::min(lo + 1, 63);
    const float *c = curve.data();
    return c[lo] * (1.0f - (idx - lo)) + c[hi] * (idx - lo);
  }

  nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>
  process_interpolation(int cur, int prev_f, FArr prev_d,
                        int next_f, FArr next_d, int stroke_idx,
                        const std::string &dtype = "auto",
                        FArr easing = FArr()) {
    return process_interpolation_advanced(cur, prev_f, prev_d, next_f, next_d,
                                          stroke_idx, dtype, easing, 0.0f, 0.0f,
                                          0.0f, false, FArr());
  }

  nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>
  process_interpolation_advanced(
      int current_frame, int prev_frame, FArr prev_data,
      int next_frame, FArr next_data, int stroke_index,
      const std::string &data_type, FArr easing_curve,
      float arc_amount, float arc_direction, float /*curvature_blend*/,
      bool use_spiral, FArr stroke_normal) {
    if (prev_data.ndim() == 0 || prev_data.shape(0) == 0 ||
        next_data.ndim() == 0 || next_data.shape(0) == 0) {
      return FArr();
    }

    const float *prev_ptr = prev_data.data();
    const float *next_ptr = next_data.data();
    size_t prev_size = prev_data.shape(0);
    size_t next_size = next_data.shape(0);

    bool is_pos = (data_type == "position") ? true
                  : (data_type == "opacity" || data_type == "radius")
                      ? false
                      : is_position_data(prev_ptr, prev_size);

    float t_linear = (next_frame != prev_frame)
                         ? (float)(current_frame - prev_frame) /
                               (float)(next_frame - prev_frame)
                         : 0.0f;
    float t = apply_easing(t_linear, easing_curve);

    if (is_pos) {
      int target_count = (int)(prev_size / 3);

      // Uniform arc-length resampling for both strokes
      std::vector<float> resampled_prev =
          resample_position_stroke(prev_ptr, prev_size, target_count);
      std::vector<float> resampled_next =
          resample_position_stroke(next_ptr, next_size, target_count);

      Point3D normal(0, 0, 1);
      if (stroke_normal.ndim() > 0 && stroke_normal.shape(0) >= 3) {
        const float *n = stroke_normal.data();
        normal = Point3D(n[0], n[1], n[2]);
      }

      std::vector<float> result;
      result.reserve(target_count * 3);

      for (int i = 0; i < target_count; ++i) {
        Point3D p(resampled_prev[i * 3], resampled_prev[i * 3 + 1],
                  resampled_prev[i * 3 + 2]);
        Point3D n(resampled_next[i * 3], resampled_next[i * 3 + 1],
                  resampled_next[i * 3 + 2]);
        Point3D r = (arc_amount < EPSILON) ? lerp3d(p, n, t)
                    : use_spiral
                        ? spiral_arc_interpolate_3d(p, n, t, arc_amount,
                                                    arc_direction, normal)
                        : bezier_arc_interpolate_3d(p, n, t, arc_amount,
                                                    arc_direction, normal);
        result.push_back(r.x);
        result.push_back(r.y);
        result.push_back(r.z);
      }
      return make_array(result);

    } else {
      int target = (int)prev_size;
      auto rp = resample_scalar(prev_ptr, prev_size, target);
      auto rn = resample_scalar(next_ptr, next_size, target);
      std::vector<float> result(target);
      for (int i = 0; i < target; ++i)
        result[i] = rp[i] * (1 - t) + rn[i] * t;
      return make_array(result);
    }
  }
};

// ============================================================================
// Python Bindings
// ============================================================================

NB_MODULE(gp_autointerpolate, m) {
  m.doc() = "GP Auto Interpolate - Arc interpolation with FTP-SC stroke correspondence";

  // ============================================================================
  // Legacy Interpolator (Linear/Arc)
  // ============================================================================
  nb::class_<Interpolator>(m, "Interpolator")
      .def(nb::init<>())
      .def("process_interpolation", &Interpolator::process_interpolation,
           nb::arg("current_frame"), nb::arg("prev_frame"),
           nb::arg("prev_data"), nb::arg("next_frame"), nb::arg("next_data"),
           nb::arg("stroke_index"), nb::arg("data_type") = std::string("auto"),
           nb::arg("easing_curve") = FArr())
      .def("process_interpolation_advanced",
           &Interpolator::process_interpolation_advanced,
           nb::arg("current_frame"), nb::arg("prev_frame"),
           nb::arg("prev_data"), nb::arg("next_frame"), nb::arg("next_data"),
           nb::arg("stroke_index"), nb::arg("data_type"),
           nb::arg("easing_curve"), nb::arg("arc_amount"),
           nb::arg("arc_direction"), nb::arg("curvature_blend"),
           nb::arg("use_spiral"), nb::arg("stroke_normal"));

  // ============================================================================
  // FTP-SC Stroke Matching
  // ============================================================================

  // Configuration
  nb::class_<ftpsc::MatcherConfig>(m, "MatcherConfig")
      .def(nb::init<>())
      .def_rw("max_alpha", &ftpsc::MatcherConfig::max_alpha)
      .def_rw("k_neighbors", &ftpsc::MatcherConfig::k_neighbors)
      .def_rw("angle_threshold", &ftpsc::MatcherConfig::angle_threshold)
      .def_rw("enable_stage_two", &ftpsc::MatcherConfig::enable_stage_two)
      .def_rw("coincident_threshold", &ftpsc::MatcherConfig::coincident_threshold)
      .def_rw("debug", &ftpsc::MatcherConfig::debug);

  // Match result
  nb::class_<ftpsc::MatchingResult>(m, "MatchingResult")
      .def_ro("num_strokes_initial", &ftpsc::MatchingResult::num_strokes_initial)
      .def_ro("num_strokes_target", &ftpsc::MatchingResult::num_strokes_target)
      .def_ro("num_matched", &ftpsc::MatchingResult::num_matched)
      .def_ro("num_unmatched_initial", &ftpsc::MatchingResult::num_unmatched_initial)
      .def_ro("num_unmatched_target", &ftpsc::MatchingResult::num_unmatched_target)
      .def_ro("stage_one_cost", &ftpsc::MatchingResult::stage_one_cost)
      .def_ro("final_cost", &ftpsc::MatchingResult::final_cost)
      .def_ro("used_stage_two", &ftpsc::MatchingResult::used_stage_two)
      .def("get_matches", [](const ftpsc::MatchingResult &result) {
          return result.final_correspondence.matches;
      }, "Get list of (initial_idx, target_idx) match pairs");

   // Schneider Bezier fitting (polyline -> cubic Beziers, separate file)
   m.def("fit_bezier", [](FArr points, float max_error) {
      if (points.ndim() == 0 || points.shape(0) == 0) return nb::list();
      const float *d = points.data();
      size_t n = points.shape(0);
      if (n % 3 != 0) return nb::list();
      auto flat = bezier_fit::fit_curve_flat(d, n, max_error);
      nb::list out;
      for (size_t i = 0; i + 11 < flat.size(); i += 12) {
         float *buf = new float[12];
         for (int k = 0; k < 12; ++k) buf[k] = flat[i + k];
         nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>> arr(buf, {12}, nb::capsule(buf, [](void *p) noexcept { delete[] (float*)p; }));
         out.append(arr);
      }
      return out;
   }, nb::arg("points"), nb::arg("max_error"),
   "Fit polyline to cubic Beziers (Schneider 1990). points=flat float32 [x,y,z,...], max_error=squared BU. Returns list of 12-float arrays [p0,c1,c2,p1].");

   m.def("fit_bezier_flat", [](FArr points, float max_error) {
      if (points.ndim() == 0 || points.shape(0) == 0) return FArr();
      const float *d = points.data();
      size_t n = points.shape(0);
      if (n % 3 != 0) return FArr();
      auto flat = bezier_fit::fit_curve_flat(d, n, max_error);
      if (flat.empty()) return FArr();
      float *buf = new float[flat.size()];
      std::copy(flat.begin(), flat.end(), buf);
      return nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>(buf, {flat.size()}, nb::capsule(buf, [](void *p) noexcept { delete[] (float*)p; }));
   }, nb::arg("points"), nb::arg("max_error"),
   "Flat variant: returns single float32 array size N*12 (curves*4*3). Empty if no fit.");

   // Main matcher class
   nb::class_<ftpsc::StrokeMatcher>(m, "StrokeMatcher")
      .def(nb::init<>())
      .def(nb::init<const ftpsc::MatcherConfig&>(), nb::arg("config"))
      .def("match", [](ftpsc::StrokeMatcher &self,
                       FArr initial_strokes,
                       FArr target_strokes) {
          // Convert numpy arrays to Stroke vectors
          // Expected format: flat array of [x0,y0, x1,y1, ..., -1, x0,y0, ...]
          // where -1 separates strokes

          const float *init_data = initial_strokes.data();
          const float *targ_data = target_strokes.data();
          size_t init_size = initial_strokes.shape(0);
          size_t targ_size = target_strokes.shape(0);

          std::vector<ftpsc::Stroke> init_strokes, targ_strokes;

          // Parse initial strokes
          std::vector<ftpsc::Vec2> current_stroke;
          for (size_t i = 0; i < init_size; i += 2) {
              float x = init_data[i];
              if (x < -0.5f) { // Separator marker (-1)
                  if (!current_stroke.empty()) {
                      ftpsc::Stroke s;
                      s.points = current_stroke;
                      init_strokes.push_back(s);
                      current_stroke.clear();
                  }
              } else if (i + 1 < init_size) {
                  float y = init_data[i + 1];
                  current_stroke.emplace_back(x, y);
              }
          }
          if (!current_stroke.empty()) {
              ftpsc::Stroke s;
              s.points = current_stroke;
              init_strokes.push_back(s);
          }

          // Parse target strokes
          current_stroke.clear();
          for (size_t i = 0; i < targ_size; i += 2) {
              float x = targ_data[i];
              if (x < -0.5f) { // Separator marker (-1)
                  if (!current_stroke.empty()) {
                      ftpsc::Stroke s;
                      s.points = current_stroke;
                      targ_strokes.push_back(s);
                      current_stroke.clear();
                  }
              } else if (i + 1 < targ_size) {
                  float y = targ_data[i + 1];
                  current_stroke.emplace_back(x, y);
              }
          }
          if (!current_stroke.empty()) {
              ftpsc::Stroke s;
              s.points = current_stroke;
              targ_strokes.push_back(s);
          }

          return self.match(init_strokes, targ_strokes);
      }, nb::arg("initial_strokes"), nb::arg("target_strokes"),
      "Match strokes between two frames using FTP-SC algorithm")
      .def("match_with_seeds", [](ftpsc::StrokeMatcher &self,
                       FArr initial_strokes,
                       FArr target_strokes,
                       nb::list seeds_list) {
          // Convert numpy arrays to Stroke vectors
          // Expected format: flat array of [x0,y0, x1,y1, ..., -1,-1, x0,y0, ...]
          // where -1,-1 separates strokes

          const float *init_data = initial_strokes.data();
          const float *targ_data = target_strokes.data();
          size_t init_size = initial_strokes.shape(0);
          size_t targ_size = target_strokes.shape(0);

          std::vector<ftpsc::Stroke> init_strokes, targ_strokes;

          // Parse initial strokes
          std::vector<ftpsc::Vec2> current_stroke;
          for (size_t i = 0; i < init_size; i += 2) {
              float x = init_data[i];
              if (x < -0.5f) { // Separator marker (-1)
                  if (!current_stroke.empty()) {
                      ftpsc::Stroke s;
                      s.points = current_stroke;
                      init_strokes.push_back(s);
                      current_stroke.clear();
                  }
              } else if (i + 1 < init_size) {
                  float y = init_data[i + 1];
                  current_stroke.emplace_back(x, y);
              }
          }
          if (!current_stroke.empty()) {
              ftpsc::Stroke s;
              s.points = current_stroke;
              init_strokes.push_back(s);
          }

          // Parse target strokes
          current_stroke.clear();
          for (size_t i = 0; i < targ_size; i += 2) {
              float x = targ_data[i];
              if (x < -0.5f) { // Separator marker (-1)
                  if (!current_stroke.empty()) {
                      ftpsc::Stroke s;
                      s.points = current_stroke;
                      targ_strokes.push_back(s);
                      current_stroke.clear();
                  }
              } else if (i + 1 < targ_size) {
                  float y = targ_data[i + 1];
                  current_stroke.emplace_back(x, y);
              }
          }
          if (!current_stroke.empty()) {
              ftpsc::Stroke s;
              s.points = current_stroke;
              targ_strokes.push_back(s);
          }

          // Parse seeds from Python list of tuples [(i, j), ...]
          std::vector<std::pair<int, int>> seeds;
          for (size_t i = 0; i < seeds_list.size(); ++i) {
              nb::tuple tuple = nb::cast<nb::tuple>(seeds_list[i]);
              int a = nb::cast<int>(tuple[0]);
              int b = nb::cast<int>(tuple[1]);
              seeds.emplace_back(a, b);
          }

          return self.match_with_seeds(init_strokes, targ_strokes, seeds);
      }, nb::arg("initial_strokes"), nb::arg("target_strokes"), nb::arg("seeds"),
      "Match strokes with user-provided seeds for initial correspondence. "
      "Seeds are (initial_idx, target_idx) pairs that guide the matching algorithm.")
      .def("get_config", &ftpsc::StrokeMatcher::get_config)
      .def("set_config", &ftpsc::StrokeMatcher::set_config, nb::arg("config"));
}
