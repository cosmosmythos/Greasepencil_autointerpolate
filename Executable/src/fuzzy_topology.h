#pragma once

#include "stroke.h"
#include <algorithm>
#include <vector>

namespace ftpsc {

// Point where another stroke connects along a reference stroke.
struct AlphaTopologyPoint {
   int stroke_index;
   Vec2 position;
   double position_along_stroke; // 0 at start, 1 at end (paper: arc_parameter)
   double distance_to_neighbor; // smallest endpoint distance (paper: mu)

   AlphaTopologyPoint(int idx, Vec2 pos, double position, double distance)
      : stroke_index(idx), position(pos), position_along_stroke(position), distance_to_neighbor(distance) {}
};

// Ordered list of strokes connected to a reference stroke.
struct AlphaTopology {
   std::vector<AlphaTopologyPoint> points;
   double alpha_threshold;

   explicit AlphaTopology(double alpha = 5.0) : alpha_threshold(alpha) {}

   bool is_compatible_with(const AlphaTopology &other) const {
      return points.size() == other.points.size();
   }

   size_t size() const { return points.size(); }
   bool empty() const { return points.empty(); }
};

// Distance from the closest endpoint of neighbor_stroke to the reference_stroke. Smaller = more connected (paper: mu).
double compute_distance_to_stroke(const Stroke &reference_stroke, const Stroke &neighbor_stroke);

// Two strokes are connected if either endpoint distance is within the connection dist (paper: alpha).
bool are_strokes_connected(const Stroke &first_stroke, const Stroke &second_stroke, double connection_dist);

// Build topology for one stroke: all connected strokes ordered along it.
AlphaTopology compute_alpha_topology(const Stroke &reference_stroke,
                                     const std::vector<Stroke> &all_strokes,
                                     int reference_index, double connection_dist);

// Try shrinking connection dist from max down to 0 until both topologies have same size.
std::pair<AlphaTopology, AlphaTopology>
make_topologies_compatible(const Stroke &first_stroke, const Stroke &second_stroke,
                           const std::vector<Stroke> &initial_strokes,
                           const std::vector<Stroke> &target_strokes,
                           int first_index, int second_index, double max_connection_dist = 5.0);

// Fix ordering when multiple connections land at same point (paper Fig.5).
void resolve_coincident_points(AlphaTopology &topology_i,
                               AlphaTopology &topology_j,
                               const std::vector<Stroke> &initial_strokes,
                               const std::vector<Stroke> &target_strokes);

} // namespace ftpsc
