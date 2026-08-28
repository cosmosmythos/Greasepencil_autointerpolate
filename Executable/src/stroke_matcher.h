/**
 * @file stroke_matcher.h
 * @brief Main API for FTP-SC stroke correspondence
 *
 * This is the top-level interface for the FTP-SC algorithm.
 * It coordinates Stage 1 (fuzzy topology preservation) and
 * Stage 2 (neighborhood competition).
 *
 * Usage:
 * ```cpp
 * StrokeMatcher matcher;
 * auto correspondence = matcher.match(initial_strokes, target_strokes);
 * ```
 */

#pragma once

#define _USE_MATH_DEFINES
#include "greedy_matcher.h"
#include "stroke.h"
#include <cmath>
#include <vector>

namespace ftpsc {

/**
 * @brief Configuration options for stroke matching
 */
struct MatcherConfig {
   // Stage 1: Fuzzy Topology
   // NOTE on units: coords are normalized to 0-10 (joint bbox, see correspondence_utils.py).
   // For 0-1 NDC, sensible is ~0.05; for 0-10, use ~0.5. Pixels ~5.
   double max_alpha = 0.5; // Default tuned for 0-10 coords

   // Stage 2: Neighborhood Competition
   int k_neighbors = 6; // Number of neighbors (paper uses 6)
   double angle_threshold =
       3.14159265358979323846 / 4.0; // θ threshold (paper uses π/4)

   // General
   bool enable_stage_two = true; // Run Stage 2 after Stage 1
   // Distance to consider points coincident (same units as coordinates)
   double coincident_threshold = 0.1; // Default tuned for 0-10 coords

  // Debug
  bool debug = false;
  int debug_level = 1; // 1=summary, 2=more detail

  // Performance
  bool use_spatial_indexing = false; // Use k-d tree for large stroke counts
  int spatial_index_threshold = 100; // Stroke count to trigger spatial indexing
};

/**
 * @brief Result of stroke matching with detailed information
 */
struct MatchingResult {
  Correspondence stage_one_correspondence;
  Correspondence final_correspondence;

  double stage_one_cost;
  double final_cost;

  int num_strokes_initial;
  int num_strokes_target;
  int num_matched;
  int num_unmatched_initial;
  int num_unmatched_target;

  bool used_stage_two;
};

/**
 * @brief Main stroke correspondence class
 *
 * Implements the complete FTP-SC algorithm:
 * - Stage 1: Fuzzy topology preserving correspondence
 * - Stage 2: Neighborhood competition for remaining strokes
 */
class StrokeMatcher {
public:
  /**
   * @brief Construct matcher with default configuration
   */
  StrokeMatcher();

  /**
   * @brief Construct matcher with custom configuration
   */
  explicit StrokeMatcher(const MatcherConfig &config);

  /**
   * @brief Match strokes between two keyframes
   *
   * This is the main entry point. It runs the complete FTP-SC algorithm.
   *
   * @param initial_strokes Strokes from initial keyframe
   * @param target_strokes Strokes from target keyframe
   * @return Matching result with correspondence and statistics
   */
  MatchingResult match(const std::vector<Stroke> &initial_strokes,
                       const std::vector<Stroke> &target_strokes);

  /**
   * @brief Match with manual seed correspondences
   *
   * Allows user to specify some correspondences manually.
   * The algorithm will respect these and match the rest.
   *
   * @param initial_strokes Strokes from initial keyframe
   * @param target_strokes Strokes from target keyframe
   * @param manual_seeds User-specified (initial_idx, target_idx) pairs
   * @return Matching result
   */
  MatchingResult
  match_with_seeds(const std::vector<Stroke> &initial_strokes,
                   const std::vector<Stroke> &target_strokes,
                   const std::vector<std::pair<int, int>> &manual_seeds);

  /**
   * @brief Run only Stage 1 (fuzzy topology preservation)
   *
   * When manual_seeds is non-empty, they are used as the initial seeds
   * for the greedy matching heap, bypassing auto-seed selection (SI).
   */
  Correspondence run_stage_one(const std::vector<Stroke> &initial_strokes,
                               const std::vector<Stroke> &target_strokes,
                               const std::vector<std::pair<int, int>> &manual_seeds = {});

  /**
   * @brief Run only Stage 2 (neighborhood competition)
   *
   * Requires Stage 1 results as input for context.
   */
  Correspondence run_stage_two(const std::vector<Stroke> &initial_strokes,
                               const std::vector<Stroke> &target_strokes,
                               const Correspondence &stage_one_result);

  /**
   * @brief Get/set configuration
   */
  const MatcherConfig &get_config() const { return config_; }
  void set_config(const MatcherConfig &config) { config_ = config; }

  /**
   * @brief Access to last matching statistics
   */
  const MatchingResult &get_last_result() const { return last_result_; }

private:
  MatcherConfig config_;
  MatchingResult last_result_;

  // Internal: SI/CD components for Stage 1
  std::vector<CandidatePair>
  stage_one_si_component(const std::vector<Stroke> &initial_strokes,
                         const std::vector<Stroke> &target_strokes,
                         const Correspondence &current_correspondence);

  std::vector<CandidatePair>
  stage_one_cd_component(const CandidatePair &seed,
                         const std::vector<Stroke> &initial_strokes,
                         const std::vector<Stroke> &target_strokes,
                         const Correspondence &current_correspondence);

  // Internal: SI/CD components for Stage 2
  std::vector<CandidatePair>
  stage_two_si_component(const std::vector<Stroke> &initial_strokes,
                         const std::vector<Stroke> &target_strokes,
                         const Correspondence &stage_one_result,
                         const Correspondence &current_correspondence);

  std::vector<CandidatePair>
  stage_two_cd_component(const CandidatePair &seed,
                         const std::vector<Stroke> &initial_strokes,
                         const std::vector<Stroke> &target_strokes,
                         const Correspondence &current_correspondence);
};

} // namespace ftpsc
