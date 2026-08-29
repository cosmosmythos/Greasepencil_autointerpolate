/**
 * @file stroke_matcher.cpp
 * @brief Implementation of StrokeMatcher class
 */

#include "stroke_matcher.h"
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
              << " seeds=" << manual_seeds.size() << "\n";
  }

  MatchingResult result;
  result.num_strokes_initial = static_cast<int>(initial_strokes.size());
  result.num_strokes_target = static_cast<int>(target_strokes.size());

  // Stage 1 with manual seeds fed directly into the greedy heap
  result.stage_one_correspondence =
      run_stage_one(initial_strokes, target_strokes, manual_seeds);
  result.stage_one_cost = result.stage_one_correspondence.average_cost();

  if (config_.debug) {
    std::cerr << "[ftpsc] stage1 (seeded): matches="
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
  }

  result.num_matched =
      static_cast<int>(result.final_correspondence.num_matches());
  result.num_unmatched_initial = result.num_strokes_initial - result.num_matched;
  result.num_unmatched_target = result.num_strokes_target - result.num_matched;

  if (config_.debug) {
    std::cerr << "[ftpsc] match_with_seeds(): final_matches="
              << result.num_matched << "\n";
  }

  last_result_ = result;
  return result;
}

} // namespace ftpsc
