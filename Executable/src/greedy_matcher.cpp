/**
 * @file greedy_matcher.cpp
 * @brief Implementation of greedy matching algorithm
 */

#include "greedy_matcher.h"
#include <iostream>

namespace ftpsc {

Correspondence GreedyMatcher::match(const std::vector<Stroke> &initial_strokes,
                                    const std::vector<Stroke> &target_strokes,
                                    SeedInitializer si_component,
                                    CandidateDeriver cd_component) {
  Correspondence correspondence(initial_strokes.size(), target_strokes.size());
  return match(initial_strokes, target_strokes, si_component, cd_component,
               correspondence);
}

Correspondence
GreedyMatcher::match(const std::vector<Stroke> &initial_strokes,
                     const std::vector<Stroke> &target_strokes,
                     SeedInitializer si_component,
                     CandidateDeriver cd_component,
                     const Correspondence &existing_correspondence) {

  Correspondence correspondence = existing_correspondence;
  std::priority_queue<CandidatePair> heap;

  // Step 1: Run SI component to get seeds
  std::vector<CandidatePair> seeds =
      si_component(initial_strokes, target_strokes, correspondence);

  // Step 2: Add seeds to correspondence and populate heap via CD
  for (const auto &seed : seeds) {
    // Only verify validity if not already matched
    bool init_free = !correspondence.is_matched_initial(seed.initial_index);
    bool targ_free = !correspondence.is_matched_target(seed.target_index);

    // Note: In some contexts (Stage 2), seeds might overlap with existing
    // correspondence. We generally assume SI returns valid, compatible matches.
    // If a seed conflicts with existing match, we skip it (keep existing).

    // If already exactly matched (same pair), just run CD (might be
    // re-proposing known match to generate neighbors) If conflicting (one
    // matched to different), skip.

    bool is_same_pair = false;
    // Check if this pair is already in matches
    // (Optimization: Correspondence struct doesn't have fast pair lookup, but
    // we can check indices) Actually, if indices are matched, we assume it's
    // this pair or conflict.

    if (init_free && targ_free) {
      // New match
      correspondence.add_match(seed.initial_index, seed.target_index,
                               -seed.matching_degree);
      is_same_pair = true; // successfully added
    } else {
      // Already matched. Is it the SAME match?
      // Since we don't store "who matched whom" easily in is_matched_*,
      // we'd need to linear search matches or add lookup vector.
      // For now, let's trust SI returns consistent seeds or new seeds.
      // If marked matched, we assume it's processed.
      // BUT we should still run CD on it if it's a seed!
      // Because Stage 2 might use Stage 1 result as seed to find NEIGHBORS.
      is_same_pair = true; // Treat as valid context for CD
    }

    if (is_same_pair) {
      // Step 3: From this match, derive candidates using CD
      std::vector<CandidatePair> candidates =
          cd_component(seed, initial_strokes, target_strokes, correspondence);

      for (const auto &cand : candidates) {
        heap.push(cand);
      }
    }
  }

  // Step 4: Process heap
  process_heap(heap, initial_strokes, target_strokes, cd_component,
               correspondence);

  return correspondence;
}

void GreedyMatcher::process_heap(std::priority_queue<CandidatePair> &heap,
                                 const std::vector<Stroke> &initial_strokes,
                                 const std::vector<Stroke> &target_strokes,
                                 CandidateDeriver cd_component,
                                 Correspondence &correspondence) {

  while (!heap.empty()) {
    CandidatePair best = heap.top();
    heap.pop();

    // Check if both start and end strokes are free
    bool init_free = !correspondence.is_matched_initial(best.initial_index);
    bool targ_free = !correspondence.is_matched_target(best.target_index);

    if (init_free && targ_free) {
      // Match found!
      correspondence.add_match(best.initial_index, best.target_index,
                               -best.matching_degree);
      
      // Debug: log accepted match (commented out to avoid spam, enable if needed)
      // std::cerr << "[C++ DEBUG] Greedy: accepted (" << best.initial_index << "->" << best.target_index << ") cost=" << (-best.matching_degree) << "\n";

      // Derive new candidates from this match
      std::vector<CandidatePair> new_candidates =
          cd_component(best, initial_strokes, target_strokes, correspondence);

      for (const auto &cand : new_candidates) {
        heap.push(cand);
      }
    }
  }
}

} // namespace ftpsc
