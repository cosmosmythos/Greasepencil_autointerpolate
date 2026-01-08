#pragma once

#define _USE_MATH_DEFINES
#include "hierarchical_interp.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace ftpsc {

/**
 * @brief Dynamic Programming Matcher for Salient Points (YF09 / LWZ04)
 *
 * Implements a DTW-style algorithm to find the optimal correspondence
 * between two sequences of salient points, respecting order and
 * minimizing a robust feature metric cost.
 */
class SalientPointMatcher {
public:
  struct Config {
    double w_angle = 1.0;      // Weight for angle difference
    double w_len = 1.0;        // Weight for relative arc length difference
    double w_importance = 0.5; // Weight for importance difference
    double skip_cost = 1.5;    // Cost to skip a feature (gap penalty)

    // YF09 Section 3.2.1 Parameter Merging implies we should match
    // based on normalized parameters.
  };

  SalientPointMatcher(const Config &config = Config()) : config_(config) {}

  /**
   * @brief Find optimal correspondence between two sets of salient points
   *
   * @param s1 Source salient points
   * @param s2 Target salient points
   * @return List of matched indices (i, j) where i is index in s1, j in s2.
   *         Unmatched points are skipped in this list.
   */
  std::vector<std::pair<size_t, size_t>>
  match(const std::vector<SalientPoint> &s1,
        const std::vector<SalientPoint> &s2);

private:
  Config config_;

  // Robust feature metric (YF09)
  double compute_cost(const SalientPoint &p1, const SalientPoint &p2);

  // Helper for 2Pi wraparound angle diff
  double angle_diff(double a1, double a2) {
    double diff = std::abs(a1 - a2);
    while (diff > M_PI)
      diff -= 2 * M_PI;
    return std::abs(diff);
  }
};

} // namespace ftpsc
