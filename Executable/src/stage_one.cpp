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
  const Stroke &S = initial_strokes[seed.initial_index];
  const Stroke &T = target_strokes[seed.target_index];

  // Compute compatible alpha-topologies
  // "We adaptively decrease alpha from 5 to 0"
  auto [top_S, top_T] = make_topologies_compatible(
      S, T, initial_strokes, target_strokes, seed.initial_index,
      seed.target_index, config_.max_alpha);

  if (config_.debug && config_.debug_level >= 2) {
    std::cerr << "[ftpsc] stage1 cd: seed (" << seed.initial_index << "->"
              << seed.target_index << ")"
              << " alpha_used=" << top_S.alpha_threshold
              << " top_size=" << top_S.size() << "\n";
  }

  // If compatible (same size), derive candidates
  if (top_S.size() == top_T.size()) {
    for (size_t k = 0; k < top_S.size(); ++k) {
      int S_k_idx = top_S.points[k].stroke_index;
      int T_k_idx = top_T.points[k].stroke_index;

      // Check if already matched
      if (current_correspondence.is_matched_initial(S_k_idx) ||
          current_correspondence.is_matched_target(T_k_idx)) {
        continue;
      }

      // Compute matching degree for this candidate pair
      const Stroke &S_k = initial_strokes[S_k_idx];
      const Stroke &T_k = target_strokes[T_k_idx];

      double cost = compute_matching_degree(S_k, T_k);

      candidates.emplace_back(S_k_idx, T_k_idx, -cost);
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
