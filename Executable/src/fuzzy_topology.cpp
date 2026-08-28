#include "fuzzy_topology.h"
#include <cmath>
#include <limits>

namespace ftpsc {

namespace detail {

// internal, testable but not public
struct SegmentClosest {
   Vec2 closest_point;         // closest on segment
   double position_on_segment; // 0 at segment_start, 1 at segment_end
   double distance;            // Euclidean
};

struct StrokeClosest {
   Vec2 closest_point;          // closest on stroke
   double position_along_stroke; // 0 at stroke start, 1 at stroke end
   double distance;             // Euclidean
};

SegmentClosest project_on_segment(const Vec2 &endpoint, const Vec2 &segment_start, const Vec2 &segment_end) {
   Vec2 segment_vector = segment_end - segment_start;
   double segment_length_squared = segment_vector.length_squared();
   if (segment_length_squared < 1e-10) {
      return {segment_start, 0.0, endpoint.distance_to(segment_start)};
   }
   Vec2 vector_to_endpoint = endpoint - segment_start;
   double position_on_segment = vector_to_endpoint.dot(segment_vector) / segment_length_squared;
   position_on_segment = std::max(0.0, std::min(1.0, position_on_segment));
   Vec2 closest_point_on_segment = segment_start + segment_vector * position_on_segment;
   return {closest_point_on_segment, position_on_segment, endpoint.distance_to(closest_point_on_segment)};
}

StrokeClosest distance_point_to_stroke(const Vec2 &endpoint, const Stroke &stroke) {
   if (stroke.points.empty()) {
      return {Vec2(0, 0), 0.0, std::numeric_limits<double>::max()};
   }
   const auto &position_along_stroke_values = stroke.get_position_along_stroke();
   double best_distance = std::numeric_limits<double>::max();
   Vec2 best_point = stroke.points[0];
   double best_position = 0.0;
   for (size_t i = 1; i < stroke.points.size(); ++i) {
      SegmentClosest segment_result = project_on_segment(endpoint, stroke.points[i - 1], stroke.points[i]);
      if (segment_result.distance < best_distance) {
         best_distance = segment_result.distance;
         best_point = segment_result.closest_point;
         double start_position = position_along_stroke_values[i - 1];
         double end_position = position_along_stroke_values[i];
         best_position = start_position + segment_result.position_on_segment * (end_position - start_position);
      }
   }
   return {best_point, best_position, best_distance};
}

} // namespace detail

double compute_distance_to_stroke(const Stroke &reference_stroke, const Stroke &neighbor_stroke) {
   if (!reference_stroke.is_valid() || !neighbor_stroke.is_valid()) {
      return std::numeric_limits<double>::infinity();
   }
   detail::StrokeClosest to_start = detail::distance_point_to_stroke(neighbor_stroke.get_start_point(), reference_stroke);
   detail::StrokeClosest to_end = detail::distance_point_to_stroke(neighbor_stroke.get_end_point(), reference_stroke);
   return std::min(to_start.distance, to_end.distance);
}

// deprecated wrappers — keep paper term // mu in comment for cross-ref
double compute_connectivity_grade(const Stroke &reference_stroke, const Stroke &neighbor_stroke) {
   return compute_distance_to_stroke(reference_stroke, neighbor_stroke); // mu
}

bool are_strokes_connected(const Stroke &first_stroke, const Stroke &second_stroke, double connection_dist) {
   double distance_first_to_second = compute_distance_to_stroke(first_stroke, second_stroke);
   if (distance_first_to_second <= connection_dist) {
      return true;
   }
   double distance_second_to_first = compute_distance_to_stroke(second_stroke, first_stroke);
   return distance_second_to_first <= connection_dist;
}

bool has_alpha_connectivity(const Stroke &first_stroke, const Stroke &second_stroke, double connection_dist) {
   return are_strokes_connected(first_stroke, second_stroke, connection_dist); // alpha
}

AlphaTopology compute_alpha_topology(const Stroke &reference_stroke,
                                     const std::vector<Stroke> &all_strokes,
                                     int reference_index, double connection_dist) {
   AlphaTopology topology(connection_dist);
   for (size_t i = 0; i < all_strokes.size(); ++i) {
      if (i == static_cast<size_t>(reference_index)) {
         continue;
      }
      const Stroke &neighbor_stroke = all_strokes[i];
      detail::StrokeClosest start_hit = detail::distance_point_to_stroke(neighbor_stroke.get_start_point(), reference_stroke);
      detail::StrokeClosest end_hit = detail::distance_point_to_stroke(neighbor_stroke.get_end_point(), reference_stroke);
      bool connected_direct = (std::min(start_hit.distance, end_hit.distance) <= connection_dist);
      bool connected_inverse = false;
      double fallback_dist = std::numeric_limits<double>::infinity();
      double fallback_position = 0.0;
      Vec2 fallback_point;
      if (!connected_direct) {
         detail::StrokeClosest inverse_start = detail::distance_point_to_stroke(reference_stroke.get_start_point(), neighbor_stroke);
         detail::StrokeClosest inverse_end = detail::distance_point_to_stroke(reference_stroke.get_end_point(), neighbor_stroke);
         if (inverse_start.distance <= connection_dist || inverse_end.distance <= connection_dist) {
            connected_inverse = true;
            if (inverse_start.distance < inverse_end.distance) {
               fallback_dist = inverse_start.distance;
               fallback_position = 0.0;
               fallback_point = reference_stroke.get_start_point();
            } else {
               fallback_dist = inverse_end.distance;
               fallback_position = 1.0;
               fallback_point = reference_stroke.get_end_point();
            }
         }
      }
      if (connected_direct || connected_inverse) {
         double distance_to_neighbor;
         double position_along_reference;
         Vec2 connection_point;
         if (connected_direct && connected_inverse) {
            double best_direct_distance = std::min(start_hit.distance, end_hit.distance);
            if (best_direct_distance < fallback_dist) {
               distance_to_neighbor = best_direct_distance;
               if (start_hit.distance < end_hit.distance) {
                  position_along_reference = start_hit.position_along_stroke;
                  connection_point = start_hit.closest_point;
               } else {
                  position_along_reference = end_hit.position_along_stroke;
                  connection_point = end_hit.closest_point;
               }
            } else {
               distance_to_neighbor = fallback_dist;
               position_along_reference = fallback_position;
               connection_point = fallback_point;
            }
         } else if (connected_direct) {
            distance_to_neighbor = std::min(start_hit.distance, end_hit.distance);
            if (start_hit.distance < end_hit.distance) {
               position_along_reference = start_hit.position_along_stroke;
               connection_point = start_hit.closest_point;
            } else {
               position_along_reference = end_hit.position_along_stroke;
               connection_point = end_hit.closest_point;
            }
         } else {
            distance_to_neighbor = fallback_dist;
            position_along_reference = fallback_position;
            connection_point = fallback_point;
         }
         topology.points.emplace_back(static_cast<int>(i), connection_point, position_along_reference, distance_to_neighbor);
      }
   }
   std::sort(topology.points.begin(), topology.points.end(),
             [](const AlphaTopologyPoint &a, const AlphaTopologyPoint &b) {
                return a.position_along_stroke < b.position_along_stroke;
             });
   return topology;
}

std::pair<AlphaTopology, AlphaTopology>
make_topologies_compatible(const Stroke &first_stroke, const Stroke &second_stroke,
                           const std::vector<Stroke> &initial_strokes,
                           const std::vector<Stroke> &target_strokes,
                           int first_index, int second_index, double max_connection_dist) {
   double step = max_connection_dist / 10.0; // finer: 0.5 -> 0.05
   if (step <= 0.0) {
      step = 0.05;
   }
   for (double connection_dist = max_connection_dist; connection_dist >= 0.0; connection_dist -= step) {
      AlphaTopology topology_first = compute_alpha_topology(first_stroke, initial_strokes, first_index, connection_dist);
      AlphaTopology topology_second = compute_alpha_topology(second_stroke, target_strokes, second_index, connection_dist);
      if (topology_first.is_compatible_with(topology_second)) {
         if (!topology_first.empty()) {
            resolve_coincident_points(topology_first, topology_second, initial_strokes, target_strokes);
         }
         return {topology_first, topology_second};
      }
   }
   return {AlphaTopology(0.0), AlphaTopology(0.0)};
}

void resolve_coincident_points(AlphaTopology &first_topology, AlphaTopology &second_topology,
                               const std::vector<Stroke> &initial_strokes,
                               const std::vector<Stroke> &target_strokes) {
   if (first_topology.size() != second_topology.size()) {
      return;
   }
   // Paper Fig.5: coincident points currently rely on stable sort by position_along_stroke.
   // Full fix would reorder by matching cost when positions are identical.
}

} // namespace ftpsc
