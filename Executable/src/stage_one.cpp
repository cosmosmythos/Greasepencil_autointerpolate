/**
 * @file stage_one.cpp
 * @brief Implementation of Stage 1 (Fuzzy Topology) components
 */

#include "fuzzy_topology.h"
#include "stroke_matcher.h"
#include <cmath>
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

   size_t n_init = initial_strokes.size();
   size_t n_targ = target_strokes.size();

   struct CandidateInfo {
      bool valid = false;
      double avg_tie = 0.0;
      size_t size = 0;
      double alpha = 0.0;
   };

   std::vector<std::vector<CandidateInfo>> grid(n_init, std::vector<CandidateInfo>(n_targ));

   // Pass 1: compute all compatible pair costs
   for (size_t i = 0; i < n_init; ++i) {
      if (current_correspondence.is_matched_initial(i)) continue;
      for (size_t j = 0; j < n_targ; ++j) {
         if (current_correspondence.is_matched_target(j)) continue;

         auto [topology_initial, topology_target] = make_topologies_compatible(
            initial_strokes[i], target_strokes[j], initial_strokes, target_strokes, (int)i, (int)j, config_.max_alpha);

         if (!topology_initial.is_compatible_with(topology_target)) continue;
         size_t size = topology_initial.size();
         if (size == 0) continue; // need at least one neighbour to judge alignment

         // average tie across k
         double avg_tie = 0.0;
         for (size_t k = 0; k < size; ++k) {
            double pos_initial = topology_initial.points[k].position_along_stroke;
            double pos_target = topology_target.points[k].position_along_stroke;
            avg_tie += std::abs(pos_initial - pos_target);
         }
         avg_tie /= (double)size;

         grid[i][j] = {true, avg_tie, size, topology_initial.alpha_threshold};
      }
   }

   // Pass 2: find the best unique seed using Lowe's Ratio Test on avg_tie
   int best_initial = -1;
   int best_target = -1;
   size_t best_topology_size = 0;
   double best_alpha_used = 0.0;
   int best_tier = 3; // 1 = size>=2 (robust), 2 = size==1 (minimal), 3 = fallback (size==0)
   double best_score = std::numeric_limits<double>::max();

   for (size_t i = 0; i < n_init; ++i) {
      if (current_correspondence.is_matched_initial(i)) continue;
      for (size_t j = 0; j < n_targ; ++j) {
         if (!grid[i][j].valid) continue;

         double min_cost1 = grid[i][j].avg_tie;
         double min_cost2 = std::numeric_limits<double>::max();

         // Find the second best target for initial stroke i from the grid
         for (size_t j2 = 0; j2 < n_targ; ++j2) {
            if (j2 == j || !grid[i][j2].valid) continue;
            if (grid[i][j2].avg_tie < min_cost2) {
               min_cost2 = grid[i][j2].avg_tie;
            }
         }

         double denom = (min_cost2 == std::numeric_limits<double>::max()) ? 1.0 : min_cost2;
         if (denom < 1e-6) denom = 1e-6;
         double ratio = min_cost1 / denom;
         double score = ratio + min_cost1; // balance uniqueness and tightness of alignment

         int tier = (grid[i][j].size >= 2) ? 1 : 2;

         if (tier < best_tier || (tier == best_tier && score < best_score)) {
            best_tier = tier;
            best_score = score;
            best_initial = (int)i;
            best_target = (int)j;
            best_topology_size = grid[i][j].size;
            best_alpha_used = grid[i][j].alpha;
         }
      }
   }

   // Fallback: if no compatible with size>0, pick max size as before
   if (best_initial == -1) {
      for (size_t i = 0; i < initial_strokes.size(); ++i) if (!current_correspondence.is_matched_initial(i)) {
         for (size_t j = 0; j < target_strokes.size(); ++j) if (!current_correspondence.is_matched_target(j)) {
            auto [topology_initial, topology_target] = make_topologies_compatible(
               initial_strokes[i], target_strokes[j], initial_strokes, target_strokes, (int)i, (int)j, config_.max_alpha);
            if (!topology_initial.is_compatible_with(topology_target)) continue;
            size_t size = topology_initial.size();
            if (size > best_topology_size) {
               best_topology_size = size;
               best_initial = (int)i; best_target = (int)j;
               best_alpha_used = topology_initial.alpha_threshold;
            }
         }
      }
   }
   if (best_initial == -1) {
      for (size_t i = 0; i < initial_strokes.size(); ++i) if (!current_correspondence.is_matched_initial(i)) {
         for (size_t j = 0; j < target_strokes.size(); ++j) if (!current_correspondence.is_matched_target(j)) {
            best_initial = (int)i; best_target = (int)j; best_topology_size = 0; break;
         }
         if (best_initial != -1) break;
      }
   }

   std::vector<CandidatePair> seeds;
   if (best_initial != -1 && best_target != -1) {
      double priority = -best_score; // heap is max, smaller score = higher priority
      seeds.emplace_back(best_initial, best_target, priority);

      if (config_.debug && config_.debug_level >= 2) {
         std::cerr << "[C++ DEBUG] SI seed centroid+tie: (" << best_initial << "->" << best_target
                   << ") size=" << best_topology_size << " score=" << best_score << " alpha=" << best_alpha_used << "\n";
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

      // No shape rank: topology order is the only trust. Use position difference as tiny tie-breaker.
      const Stroke &candidate_initial_stroke = initial_strokes[candidate_initial_index];
      const Stroke &candidate_target_stroke = target_strokes[candidate_target_index];
      (void)candidate_initial_stroke; (void)candidate_target_stroke;
      double position_initial = topology_initial.points[k].position_along_stroke;
      double position_target = topology_target.points[k].position_along_stroke;
      double tie_cost = std::abs(position_initial - position_target); // 0 when same spot
      double priority = -tie_cost; // heap is max, so smaller diff = higher priority
      candidates.emplace_back(candidate_initial_index, candidate_target_index, priority);
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
                             const std::vector<Stroke> &target_strokes,
                             const std::vector<std::pair<int, int>> &manual_seeds) {

  GreedyMatcher matcher;

  using namespace std::placeholders;
  auto cd =
      std::bind(&StrokeMatcher::stage_one_cd_component, this, _1, _2, _3, _4);

  if (!manual_seeds.empty()) {
    // Manual seeds provided: use them directly as SI, bypassing auto-seed selection
    auto si_manual = [&manual_seeds, this](
        const std::vector<Stroke> &init, const std::vector<Stroke> &targ,
        const Correspondence &corr) -> std::vector<CandidatePair> {
      std::vector<CandidatePair> seeds;
      for (const auto &seed : manual_seeds) {
        int i = seed.first;
        int j = seed.second;
        if (i < 0 || i >= static_cast<int>(init.size()) ||
            j < 0 || j >= static_cast<int>(targ.size()))
          continue;
        if (corr.is_matched_initial(i) || corr.is_matched_target(j))
          continue;
        // Highest priority so they are processed first
        seeds.emplace_back(i, j, 1e9);
      }
      if (config_.debug) {
        std::cerr << "[ftpsc] stage1 SI: using " << seeds.size()
                  << " manual seeds (bypassing auto-seed)\n";
      }
      return seeds;
    };
    return matcher.match(initial_strokes, target_strokes, si_manual, cd);
  }

  // No manual seeds: fall back to auto-seed selection
  auto si = std::bind(&StrokeMatcher::stage_one_si_component, this, _1, _2, _3);
  return matcher.match(initial_strokes, target_strokes, si, cd);
}

} // namespace ftpsc

