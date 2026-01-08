/**
 * @file fuzzy_topology.cpp
 * @brief Implementation of α-Topology computation
 */

#include "fuzzy_topology.h"
#include <cmath>
#include <limits>
#include <tuple>


namespace ftpsc {

namespace {

/**
 * @brief Project point p onto line segment ab
 * @return Tuple of (closest_point, t, dist_sq) where t is in [0,1]
 */
std::tuple<Vec2, double, double>
project_on_segment(const Vec2 &p, const Vec2 &a, const Vec2 &b) {

  Vec2 ab = b - a;
  double len_sq = ab.length_squared();

  if (len_sq < 1e-10) {
    // Segment is a point
    return {a, 0.0, p.distance_to(a) * p.distance_to(a)};
  }

  Vec2 ap = p - a;
  double t = ap.dot(ab) / len_sq;
  t = std::max(0.0, std::min(1.0, t));

  Vec2 closest = a + ab * t;
  double dist_sq = p.distance_to(closest) * p.distance_to(closest);

  return {closest, t, dist_sq};
}

/**
 * @brief Find closest point on stroke S to point p
 * @return Tuple of (closest_point, arc_parameter, dist)
 */
std::tuple<Vec2, double, double> distance_point_to_stroke(const Vec2 &p,
                                                          const Stroke &S) {

  if (S.points.empty()) {
    return {Vec2(0, 0), 0.0, std::numeric_limits<double>::max()};
  }

  const auto &params = S.get_arc_parameters();

  double min_dist_sq = std::numeric_limits<double>::max();
  Vec2 best_point = S.points[0];
  double best_param = 0.0;

  // Check all segments
  for (size_t i = 1; i < S.points.size(); ++i) {
    auto [closest, t, dist_sq] =
        project_on_segment(p, S.points[i - 1], S.points[i]);

    if (dist_sq < min_dist_sq) {
      min_dist_sq = dist_sq;
      best_point = closest;

      // Interpolate global arc parameter
      double p0 = params[i - 1];
      double p1 = params[i];
      best_param = p0 + t * (p1 - p0);
    }
  }

  return {best_point, best_param, std::sqrt(min_dist_sq)};
}

} // anonymous namespace

// =============================================================================
// Public API Implementation
// =============================================================================

double compute_connectivity_grade(const Stroke &S, const Stroke &Si) {
  if (!S.is_valid() || !Si.is_valid()) {
    return std::numeric_limits<double>::infinity();
  }

  // μ_S(S_i) = min distance from S_i's endpoints to S
  Vec2 start = Si.get_start();
  Vec2 end = Si.get_end();

  auto [p1, t1, d1] = distance_point_to_stroke(start, S);
  auto [p2, t2, d2] = distance_point_to_stroke(end, S);

  return std::min(d1, d2);
}

bool has_alpha_connectivity(const Stroke &S, const Stroke &Si, double alpha) {
  double mu_S_Si = compute_connectivity_grade(S, Si);
  if (mu_S_Si <= alpha)
    return true;

  double mu_Si_S = compute_connectivity_grade(Si, S);
  if (mu_Si_S <= alpha)
    return true;

  return false;
}

AlphaTopology compute_alpha_topology(const Stroke &reference_stroke,
                                     const std::vector<Stroke> &all_strokes,
                                     int reference_index, double alpha) {

  AlphaTopology topology(alpha);

  // Check all other strokes for connectivity
  for (size_t i = 0; i < all_strokes.size(); ++i) {
    if (i == static_cast<size_t>(reference_index))
      continue;

    const Stroke &Si = all_strokes[i];

    // Compute strict connectivity grade to find WHERE it connects
    // Determining the connection point: "point on S closest to an endpoint of
    // Si"

    Vec2 start = Si.get_start();
    Vec2 end = Si.get_end();

    auto [p1, t1, d1] = distance_point_to_stroke(start, reference_stroke);
    auto [p2, t2, d2] = distance_point_to_stroke(end, reference_stroke);

    // We consider it connected if min(d1, d2) <= alpha OR inverted check
    // passes. Paper Definition 2 says: "sequence of α-connected strokes...
    // ordered by their connection points on S"

    // If connected via S->Si check (Si endpoints close to S)
    bool connected_direct = (std::min(d1, d2) <= alpha);

    // If connected via Si->S check (S endpoints close to Si), we need to find
    // point on S In that case, an endpoint of S is close to Si. So the
    // connection point on S is that endpoint of S (param 0.0 or 1.0).
    bool connected_inverse = false;
    double dist_inv = std::numeric_limits<double>::infinity();
    double param_inv = 0.0;
    Vec2 pos_inv;

    if (!connected_direct) {
      // Check inverse
      Vec2 s_start = reference_stroke.get_start();
      Vec2 s_end = reference_stroke.get_end();

      auto [q1, u1, di1] = distance_point_to_stroke(s_start, Si);
      auto [q2, u2, di2] = distance_point_to_stroke(s_end, Si);

      if (di1 <= alpha || di2 <= alpha) {
        connected_inverse = true;
        if (di1 < di2) {
          dist_inv = di1;
          param_inv = 0.0; // Start of S
          pos_inv = s_start;
        } else {
          dist_inv = di2;
          param_inv = 1.0; // End of S
          pos_inv = s_end;
        }
      }
    }

    if (connected_direct || connected_inverse) {
      // Determine best connection point
      double grade;
      double param;
      Vec2 pos;

      if (connected_direct && connected_inverse) {
        // Both valid, pick strongest (closest)
        double min_direct = std::min(d1, d2);
        if (min_direct < dist_inv) {
          grade = min_direct;
          if (d1 < d2) {
            param = t1;
            pos = p1;
          } else {
            param = t2;
            pos = p2;
          }
        } else {
          grade = dist_inv;
          param = param_inv;
          pos = pos_inv;
        }
      } else if (connected_direct) {
        grade = std::min(d1, d2);
        if (d1 < d2) {
          param = t1;
          pos = p1;
        } else {
          param = t2;
          pos = p2;
        }
      } else {
        grade = dist_inv;
        param = param_inv;
        pos = pos_inv;
      }

      topology.points.emplace_back(static_cast<int>(i), pos, param, grade);
    }
  }

  // Sort by arc parameter to establish topological order
  std::sort(topology.points.begin(), topology.points.end(),
            [](const AlphaTopologyPoint &a, const AlphaTopologyPoint &b) {
              return a.arc_parameter < b.arc_parameter;
            });

  return topology;
}

std::pair<AlphaTopology, AlphaTopology>
make_topologies_compatible(const Stroke &stroke_i, const Stroke &stroke_j,
                           const std::vector<Stroke> &initial_strokes,
                           const std::vector<Stroke> &target_strokes,
                           int index_i, int index_j, double max_alpha) {

  // Paper uses integer α in [5..0]. For continuous coordinate systems (e.g. NDC),
  // we decrease α in fixed steps.
  double step = max_alpha / 5.0;
  if (step <= 0.0)
    step = 1.0;

  for (double alpha = max_alpha; alpha >= 0.0; alpha -= step) {
    AlphaTopology top_i =
        compute_alpha_topology(stroke_i, initial_strokes, index_i, alpha);
    AlphaTopology top_j =
        compute_alpha_topology(stroke_j, target_strokes, index_j, alpha);

    if (top_i.is_compatible_with(top_j)) {
      // Resolve coincident points to ensure stable matching
      if (!top_i.empty()) {
        resolve_coincident_points(top_i, top_j, initial_strokes,
                                  target_strokes);
      }
      return {top_i, top_j};
    }
  }

  // Fallback: return empty topologies (incompatible)
  return {AlphaTopology(0.0), AlphaTopology(0.0)};
}

void resolve_coincident_points(AlphaTopology &top_i, AlphaTopology &top_j,
                               const std::vector<Stroke> &initial_strokes,
                               const std::vector<Stroke> &target_strokes) {
  // This function handles edge cases where multiple strokes connect at
  // effectively the same point (e.g., crossing point).
  // The paper (Section 3.3, Fig 5) suggests reordering based on best match
  // if positions are coincident.

  // Assuming 1-to-1 correspondence (compatibility checked)
  if (top_i.size() != top_j.size())
    return;

  // Simple heuristic: if parameters are identical, stable sort by original
  // index A fully rigorous implementation would try to minimize total matching
  // cost between the sequence of connected strokes. For now, we rely on the
  // primary sort by parameter.

  // Advanced coincident point resolution (for future enhancement)
  // cases. Current implementation relies on stable sort of
  // compute_alpha_topology.
}

} // namespace ftpsc
