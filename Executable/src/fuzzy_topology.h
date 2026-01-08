/**
 * @file fuzzy_topology.h
 * @brief α-Topology computation for FTP-SC Stage 1
 *
 * Implements the fuzzy topology preservation mechanism from:
 * Yang et al. 2018 "FTP-SC: Fuzzy Topology Preserving Stroke Correspondence"
 * Section 3.1 (Fuzzy Topology)  and Section 3.3 (Stage One)
 *
 * Key concepts:
 * - α-connectivity: Two strokes are α-connected if close enough (within α
 * distance)
 * - α-topology: Ordered sequence of α-connected strokes along a reference
 * stroke
 * - Topology compatibility: Two α-topologies compatible if same cardinality
 */

#pragma once

#include "stroke.h"
#include <algorithm>
#include <vector>


namespace ftpsc {

/**
 * @brief A point in the α-topology of a stroke
 *
 * Represents a connection to another stroke at a specific position.
 * This corresponds to Definition 2 in the paper.
 */
struct AlphaTopologyPoint {
  int stroke_index; // Index of the connected stroke
  Vec2 position;    // Position on the reference stroke where connection occurs
  double arc_parameter;      // Parameter t ∈ [0,1] along reference stroke
  double connectivity_grade; // μ value (minimum distance)

  AlphaTopologyPoint(int idx, Vec2 pos, double param, double grade)
      : stroke_index(idx), position(pos), arc_parameter(param),
        connectivity_grade(grade) {}
};

/**
 * @brief α-Topology of a stroke
 *
 * An ordered sequence of topology points, sorted by position along the stroke.
 * This is the F_α^S from Definition 2 in the paper.
 */
struct AlphaTopology {
  std::vector<AlphaTopologyPoint> points;
  double alpha_threshold; // The α value used to construct this topology

  explicit AlphaTopology(double alpha = 5.0) : alpha_threshold(alpha) {}

  /**
   * @brief Check if this topology is compatible with another
   *
   * From paper: "Two α-topologies are compatible if they have
   * the same cardinality (same number of connection points)"
   */
  bool is_compatible_with(const AlphaTopology &other) const {
    return points.size() == other.points.size();
  }

  size_t size() const { return points.size(); }

  bool empty() const { return points.empty(); }
};

/**
 * @brief Compute connectivity grade μ_S(S_i)
 *
 * From paper Definition 1:
 * μ_S(S_i) = minimum distance from S_i's endpoints to stroke S
 *
 * @param S Reference stroke
 * @param S_i Test stroke
 * @return Connectivity grade (lower = more connected)
 */
double compute_connectivity_grade(const Stroke &S, const Stroke &S_i);

/**
 * @brief Check if two strokes have α-connectivity
 *
 * Two strokes S and S_i are α-connected if:
 * μ_S(S_i) ≤ α  OR  μ_S_i(S) ≤ α
 *
 * (Either S_i's endpoint is close to S, or S's endpoint is close to S_i)
 */
bool has_alpha_connectivity(const Stroke &S, const Stroke &S_i, double alpha);

/**
 * @brief Compute α-topology for a stroke
 *
 * Finds all strokes in the collection that have α-connectivity to the
 * reference stroke, and orders them by position along the reference stroke.
 *
 * This is Algorithm 2 (implicit) from the paper, building F_α^S.
 *
 * @param reference_stroke The stroke to build topology for (S in the paper)
 * @param all_strokes Complete collection of strokes in the frame
 * @param reference_index Index of reference_stroke in all_strokes (to skip
 * self)
 * @param alpha The α threshold for connectivity
 * @return The α-topology: ordered list of connected strokes
 */
AlphaTopology compute_alpha_topology(const Stroke &reference_stroke,
                                     const std::vector<Stroke> &all_strokes,
                                     int reference_index, double alpha);

/**
 * @brief Make two topologies compatible by decreasing α
 *
 * From paper Section 3.3:
 * "We adaptively decrease α from 5 to 0 until we find compatible topologies"
 *
 * Tries α = max_alpha, max_alpha-1, ..., 0 until compatible or α=0.
 *
 * @param stroke_i Stroke from initial frame
 * @param stroke_j Stroke from target frame
 * @param initial_strokes All strokes in initial frame
 * @param target_strokes All strokes in target frame
 * @param index_i Index of stroke_i in initial_strokes
 * @param index_j Index of stroke_j in target_strokes
 * @param max_alpha Starting α value (default 5)
 * @return Pair of compatible topologies, or empty topologies if incompatible
 */
std::pair<AlphaTopology, AlphaTopology>
make_topologies_compatible(const Stroke &stroke_i, const Stroke &stroke_j,
                           const std::vector<Stroke> &initial_strokes,
                           const std::vector<Stroke> &target_strokes,
                           int index_i, int index_j, double max_alpha = 5.0);

/**
 * @brief Handle coincident points (Figure 5 in paper)
 *
 * When multiple topology points have the same (or very close) positions,
 * they need to be reordered based on matching quality.
 *
 * This resolves ambiguities in stroke ordering at junction points.
 */
void resolve_coincident_points(AlphaTopology &topology_i,
                               AlphaTopology &topology_j,
                               const std::vector<Stroke> &initial_strokes,
                               const std::vector<Stroke> &target_strokes);

} // namespace ftpsc
