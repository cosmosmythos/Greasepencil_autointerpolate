/**
 * @file stage_one.cpp
 * @brief Implementation of Stage 1 (Fuzzy Topology) components
 */

#include "fuzzy_topology.h"
#include "similarity_transform.h"
#include "stroke_matcher.h"
#include <iostream>
#include <limits>


namespace ftpsc {

// =============================================================================
// Stage 1: SI Component (Seed Initialization)
// =============================================================================

std::vector<CandidatePair> StrokeMatcher::stage_one_si_component(
    const std::vector<Stroke> &initial_strokes,
    const std::vector<Stroke> &target_strokes,
    const Correspondence &current_correspondence) {

  // Paper Section 3.3:
  // "We calculate the matching degree for all pairs... The pair with the
  // smallest matching distance d_min is selected as a seed."

  // Check if we already have matches (should be empty for Stage 1 start,
  // but generic interface supports existing matches).
  // If correspondence is empty, find global best.

  // Optimization: If N*M is large, this is expensive O(N*M).
  // Paper implies we do this once at the start.

  double min_cost = std::numeric_limits<double>::max();
  int best_i = -1;
  int best_j = -1;

  for (size_t i = 0; i < initial_strokes.size(); ++i) {
    if (current_correspondence.is_matched_initial(i))
      continue;

    for (size_t j = 0; j < target_strokes.size(); ++j) {
      if (current_correspondence.is_matched_target(j))
        continue;

      // Optimization: Filter by bounding box or simple heuristic first?
      // For now, full compute as per paper.

      double cost =
          compute_matching_degree(initial_strokes[i], target_strokes[j]);

      // Debug: log first few costs in detail
      if (config_.debug && config_.debug_level >= 3 && i < 3 && j < 3) {
        std::cerr << "[C++ DEBUG] SI cost(" << i << "," << j << ") = " << cost 
                  << " | pts: " << initial_strokes[i].points.size() 
                  << " vs " << target_strokes[j].points.size() << "\n";
      }

      if (cost < min_cost) {
        min_cost = cost;
        best_i = i;
        best_j = j;
      }
    }
  }

  std::vector<CandidatePair> seeds;
  if (best_i != -1 && best_j != -1) {
    // Return best pair. Negative cost because CandidatePair stores "matching
    // degree" (higher is better) while matching function returns "cost" (lower
    // is better). To be consistent with max-heap, we use negative cost.
    seeds.emplace_back(best_i, best_j, -min_cost);
    
    if (config_.debug && config_.debug_level >= 2) {
      std::cerr << "[C++ DEBUG] SI selected seed: (" << best_i << "->" << best_j 
                << ") with cost=" << min_cost << "\n";
    }
  }

  return seeds;
}

// =============================================================================
// Stage 1: CD Component (Candidate Derivation)
// =============================================================================

std::vector<CandidatePair> StrokeMatcher::stage_one_cd_component(
    const CandidatePair &seed, const std::vector<Stroke> &initial_strokes,
    const std::vector<Stroke> &target_strokes,
    const Correspondence &current_correspondence) {

  std::vector<CandidatePair> candidates;

  // Seed strokes
  const Stroke &seed_initial_stroke = initial_strokes[seed.initial_index];
  const Stroke &seed_target_stroke = target_strokes[seed.target_index];

  // Compute compatible topologies shrinking connection distance from maximum to 0
  auto [topology_initial, topology_target] = make_topologies_compatible(
      seed_initial_stroke, seed_target_stroke, initial_strokes, target_strokes, seed.initial_index,
      seed.target_index, config_.max_alpha);

  if (config_.debug && config_.debug_level >= 2) {
    std::cerr << "[ftpsc] stage1 cd: seed (" << seed.initial_index << "->"
              << seed.target_index << ")"
              << " alpha_used=" << topology_initial.alpha_threshold
              << " top_size=" << topology_initial.size() << "\n";
  }

  // If compatible (same size), derive candidates
  if (topology_initial.size() == topology_target.size()) {
    for (size_t k = 0; k < topology_initial.size(); ++k) {
      int candidate_initial_index = topology_initial.points[k].stroke_index;
      int candidate_target_index = topology_target.points[k].stroke_index;

      // Check if already matched
      if (current_correspondence.is_matched_initial(candidate_initial_index) ||
          current_correspondence.is_matched_target(candidate_target_index)) {
        continue;
      }

      // Compute matching degree for this candidate pair
      const Stroke &candidate_initial_stroke = initial_strokes[candidate_initial_index];
      const Stroke &candidate_target_stroke = target_strokes[candidate_target_index];

      double cost = compute_matching_degree(candidate_initial_stroke, candidate_target_stroke);

      candidates.emplace_back(candidate_initial_index, candidate_target_index, -cost);
    }
  }

  // Debug: dump all candidates from this seed
  if (config_.debug && config_.debug_level >= 3) {
    std::cerr << "[C++ DEBUG] CD candidates from seed (" << seed.initial_index 
              << "->" << seed.target_index << "):\n";
    for (const auto &c : candidates) {
      std::cerr << "    (" << c.initial_index << "->" << c.target_index 
                << ") cost=" << (-c.matching_degree) << "\n";
    }
  }

  return candidates;
}

// =============================================================================
// Stage 1: Runner
// =============================================================================

Correspondence
StrokeMatcher::run_stage_one(const std::vector<Stroke> &initial_strokes,
                             const std::vector<Stroke> &target_strokes) {

  GreedyMatcher matcher;

  // Bind member functions to match function signature
  using namespace std::placeholders;

  auto si = std::bind(&StrokeMatcher::stage_one_si_component, this, _1, _2, _3);
  auto cd =
      std::bind(&StrokeMatcher::stage_one_cd_component, this, _1, _2, _3, _4);

  return matcher.match(initial_strokes, target_strokes, si, cd);
}

} // namespace ftpsc
