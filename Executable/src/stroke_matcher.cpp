/**
 * @file stroke_matcher.cpp
 * @brief Implementation of StrokeMatcher class
 */

#include "stroke_matcher.h"
#include "similarity_transform.h"
#include <iostream>

namespace ftpsc {

StrokeMatcher::StrokeMatcher() {
  // Default config
}

StrokeMatcher::StrokeMatcher(const MatcherConfig &config) : config_(config) {}

MatchingResult StrokeMatcher::match(const std::vector<Stroke> &initial_strokes,
                                    const std::vector<Stroke> &target_strokes) {

  if (config_.debug) {
    std::cerr << "[ftpsc] match(): initial=" << initial_strokes.size()
              << " target=" << target_strokes.size()
              << " max_alpha=" << config_.max_alpha
              << " coincident_threshold=" << config_.coincident_threshold
              << " k_neighbors=" << config_.k_neighbors
              << " angle_threshold=" << config_.angle_threshold
              << " stage2=" << (config_.enable_stage_two ? "on" : "off")
              << "\n";
  }

  MatchingResult result;
  result.num_strokes_initial = static_cast<int>(initial_strokes.size());
  result.num_strokes_target = static_cast<int>(target_strokes.size());

  // Stage 1
  result.stage_one_correspondence =
      run_stage_one(initial_strokes, target_strokes);
  result.stage_one_cost = result.stage_one_correspondence.average_cost();
  if (config_.debug) {
    std::cerr << "[ftpsc] stage1: matches="
              << result.stage_one_correspondence.num_matches()
              << " avg_cost=" << result.stage_one_cost << "\n";
  }

  // Initialize final results with Stage 1
  result.final_correspondence = result.stage_one_correspondence;
  result.final_cost = result.stage_one_cost;
  result.used_stage_two = false;

  // Stage 2 (Optional)
  if (config_.enable_stage_two) {
    result.final_correspondence = run_stage_two(
        initial_strokes, target_strokes, result.stage_one_correspondence);
    result.final_cost = result.final_correspondence.average_cost();
    result.used_stage_two = true;
    if (config_.debug) {
      std::cerr << "[ftpsc] stage2: matches="
                << result.final_correspondence.num_matches()
                << " avg_cost=" << result.final_cost << "\n";
    }
  }

  result.num_matched =
      static_cast<int>(result.final_correspondence.num_matches());
  result.num_unmatched_initial = result.num_strokes_initial - result.num_matched;
  result.num_unmatched_target = result.num_strokes_target - result.num_matched;

  last_result_ = result;
  return result;
}

MatchingResult StrokeMatcher::match_with_seeds(
    const std::vector<Stroke> &initial_strokes,
    const std::vector<Stroke> &target_strokes,
    const std::vector<std::pair<int, int>> &manual_seeds) {

  if (config_.debug) {
    std::cerr << "[ftpsc] match_with_seeds(): initial=" << initial_strokes.size()
              << " target=" << target_strokes.size()
              << " manual_seeds=" << manual_seeds.size() << "\n";
  }

  MatchingResult result;
  result.num_strokes_initial = static_cast<int>(initial_strokes.size());
  result.num_strokes_target = static_cast<int>(target_strokes.size());

  // Create initial correspondence with manual seeds
  Correspondence initial_correspondence(initial_strokes.size(),
                                        target_strokes.size());

  // Pre-populate with manual seeds
  for (const auto &seed : manual_seeds) {
    int i = seed.first;
    int j = seed.second;

    // Validate indices
    if (i < 0 || i >= static_cast<int>(initial_strokes.size()) || j < 0 ||
        j >= static_cast<int>(target_strokes.size())) {
      continue;
    }

    // Check if already matched
    if (initial_correspondence.is_matched_initial(i) ||
        initial_correspondence.is_matched_target(j)) {
      continue;
    }

    // Compute cost for this seed
    double cost = compute_matching_degree(initial_strokes[i], target_strokes[j]);
    initial_correspondence.add_match(i, j, cost);
  }

  if (config_.debug) {
    std::cerr << "[ftpsc] Pre-seeded matches: "
              << initial_correspondence.num_matches() << "\n";
  }

  // Stage 1: Run with existing seeds as context
  result.stage_one_correspondence =
      run_stage_one(initial_strokes, target_strokes);

  // Merge manual seeds with Stage 1 results
  Correspondence merged(initial_strokes.size(), target_strokes.size());

  // Add manual seeds first
  for (const auto &seed : manual_seeds) {
    int i = seed.first;
    int j = seed.second;
    if (i >= 0 && i < static_cast<int>(initial_strokes.size()) && j >= 0 &&
        j < static_cast<int>(target_strokes.size())) {
      if (!merged.is_matched_initial(i) && !merged.is_matched_target(j)) {
        double cost =
            compute_matching_degree(initial_strokes[i], target_strokes[j]);
        merged.add_match(i, j, cost);
      }
    }
  }

  // Add Stage 1 matches that don't conflict
  for (const auto &match : result.stage_one_correspondence.matches) {
    int i = match.first;
    int j = match.second;
    if (!merged.is_matched_initial(i) && !merged.is_matched_target(j)) {
      double cost =
          compute_matching_degree(initial_strokes[i], target_strokes[j]);
      merged.add_match(i, j, cost);
    }
  }

  result.stage_one_correspondence = merged;
  result.stage_one_cost = result.stage_one_correspondence.average_cost();

  // Initialize final results
  result.final_correspondence = result.stage_one_correspondence;
  result.final_cost = result.stage_one_cost;
  result.used_stage_two = false;

  // Stage 2 (Optional)
  if (config_.enable_stage_two) {
    result.final_correspondence = run_stage_two(
        initial_strokes, target_strokes, result.stage_one_correspondence);
    result.final_cost = result.final_correspondence.average_cost();
    result.used_stage_two = true;
  }

  result.num_matched =
      static_cast<int>(result.final_correspondence.num_matches());
  result.num_unmatched_initial = result.num_strokes_initial - result.num_matched;
  result.num_unmatched_target = result.num_strokes_target - result.num_matched;

  if (config_.debug) {
    std::cerr << "[ftpsc] match_with_seeds(): final_matches="
              << result.num_matched << " (manual: " << manual_seeds.size()
              << ", auto: " << (result.num_matched - manual_seeds.size())
              << ")\n";
  }

  last_result_ = result;
  return result;
}

} // namespace ftpsc
