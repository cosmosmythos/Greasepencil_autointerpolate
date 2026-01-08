/**
 * @file greedy_matcher.h
 * @brief Greedy matching algorithm (Algorithm 1 from FTP-SC)
 *
 * Implements the core greedy matching framework from:
 * Yang et al. 2018, Section 3.2 "Self-Growing Greedy Matching"
 *
 * The algorithm consists of three components:
 * - SI (Seed Initialization): Generate initial seed correspondences
 * - CD (Candidate Derivation): Derive new candidates from seeds
 * - SP (Seed Picking): Select best candidate (max-heap)
 *
 * Different implementations of SI and CD create Stage 1 vs Stage 2.
 */

#pragma once

#include "stroke.h"
#include <functional>
#include <queue>
#include <unordered_set>
#include <vector>

namespace ftpsc {

/**
 * @brief A candidate stroke pair with matching degree
 *
 * Represents a potential correspondence between an initial stroke
 * and a target stroke, with an associated quality score.
 */
struct CandidatePair {
  int initial_index;      // Index into initial_strokes
  int target_index;       // Index into target_strokes
  double matching_degree; // Higher = better match (negative of cost)

  CandidatePair(int i, int j, double degree)
      : initial_index(i), target_index(j), matching_degree(degree) {}

  // For max-heap (priority_queue): higher matching_degree = higher priority
  bool operator<(const CandidatePair &other) const {
    return matching_degree < other.matching_degree;
  }
};

/**
 * @brief Result of stroke correspondence
 *
 * Stores the one-to-one mapping between initial and target strokes.
 */
struct Correspondence {
  std::vector<std::pair<int, int>> matches; // (initial_idx, target_idx) pairs
  std::vector<bool> matched_initial;        // Which initial strokes are matched
  std::vector<bool> matched_target;         // Which target strokes are matched
  double total_cost;                        // Sum of matching costs

  Correspondence(size_t n_initial, size_t n_target)
      : matched_initial(n_initial, false), matched_target(n_target, false),
        total_cost(0.0) {
    matches.reserve(std::min(n_initial, n_target));
  }

  Correspondence() : Correspondence(0, 0) {}

  /**
   * @brief Add a correspondence
   */
  void add_match(int initial_idx, int target_idx, double cost) {
    matches.emplace_back(initial_idx, target_idx);
    matched_initial[initial_idx] = true;
    matched_target[target_idx] = true;
    total_cost += cost;
  }

  /**
   * @brief Check if an initial stroke is already matched
   */
  bool is_matched_initial(int idx) const {
    return idx >= 0 && idx < static_cast<int>(matched_initial.size()) &&
           matched_initial[idx];
  }

  /**
   * @brief Check if a target stroke is already matched
   */
  bool is_matched_target(int idx) const {
    return idx >= 0 && idx < static_cast<int>(matched_target.size()) &&
           matched_target[idx];
  }

  /**
   * @brief Get number of matches established
   */
  size_t num_matches() const { return matches.size(); }

  /**
   * @brief Get average matching cost
   */
  double average_cost() const {
    return matches.empty() ? 0.0 : (total_cost / matches.size());
  }
};

/**
 * @brief SI-Component function signature
 *
 * Generates initial seed correspondences.
 *
 * @param initial_strokes Strokes from initial keyframe
 * @param target_strokes Strokes from target keyframe
 * @param current_correspondence Current matching state
 * @return Vector of seed candidate pairs
 */
using SeedInitializer = std::function<std::vector<CandidatePair>(
    const std::vector<Stroke> &initial_strokes,
    const std::vector<Stroke> &target_strokes,
    const Correspondence &current_correspondence)>;

/**
 * @brief CD-Component function signature
 *
 * Derives new candidate pairs from a seed correspondence.
 *
 * @param seed The seed pair that was just matched
 * @param initial_strokes Strokes from initial keyframe
 * @param target_strokes Strokes from target keyframe
 * @param current_correspondence Current matching state
 * @return Vector of derived candidate pairs
 */
using CandidateDeriver = std::function<std::vector<CandidatePair>(
    const CandidatePair &seed, const std::vector<Stroke> &initial_strokes,
    const std::vector<Stroke> &target_strokes,
    const Correspondence &current_correspondence)>;

/**
 * @brief Greedy matching algorithm (Algorithm 1 from paper)
 *
 * The core matching algorithm that takes SI and CD components as inputs
 * and produces a one-to-one correspondence.
 *
 * Pseudocode from paper:
 * ```
 * 1. heap h ← empty priority queue
 * 2. seeds ← SI-component
 * 3. For each seed: push CD-component(seed) into h
 * 4. While h not empty:
 *      (Si, Tj) ← h.pop()
 *      if both unmatched:
 *          match Si to Tj
 *          push CD-component(Si, Tj) into h
 * ```
 */
class GreedyMatcher {
public:
  /**
   * @brief Run the greedy matching algorithm
   *
   * @param initial_strokes Strokes from initial keyframe
   * @param target_strokes Strokes from target keyframe
   * @param si_component Seed initialization strategy
   * @param cd_component Candidate derivation strategy
   * @return Complete correspondence
   */
  Correspondence match(const std::vector<Stroke> &initial_strokes,
                       const std::vector<Stroke> &target_strokes,
                       SeedInitializer si_component,
                       CandidateDeriver cd_component);

  /**
   * @brief Run matching with optional existing correspondence
   *
   * This is used in Stage 2, where we provide Stage 1 results as context.
   */
  Correspondence match(const std::vector<Stroke> &initial_strokes,
                       const std::vector<Stroke> &target_strokes,
                       SeedInitializer si_component,
                       CandidateDeriver cd_component,
                       const Correspondence &existing_correspondence);

private:
  // Internal helper: process the priority queue
  void process_heap(std::priority_queue<CandidatePair> &heap,
                    const std::vector<Stroke> &initial_strokes,
                    const std::vector<Stroke> &target_strokes,
                    CandidateDeriver cd_component,
                    Correspondence &correspondence);
};

} // namespace ftpsc
