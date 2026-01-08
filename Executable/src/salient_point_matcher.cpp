#include "salient_point_matcher.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>


namespace ftpsc {

SalientPointMatcher::SalientPointMatcher(const Config &config) : config_(config) {}

double SalientPointMatcher::compute_cost(const SalientPoint &p1,
                                         const SalientPoint &p2) {
  double cost = 0.0;

  // 1. Angle Difference (Curvature/Turning Angle)
  double a_diff = angle_diff(p1.turning_angle, p2.turning_angle);
  cost += config_.w_angle * a_diff;

  // 2. Relative Arc Length Difference
  // Helps roughly align the start, middle, and end
  double l_diff = std::abs(p1.arc_length_ratio - p2.arc_length_ratio);
  cost += config_.w_len * l_diff;

  // 3. Importance Difference
  double i_diff = std::abs(p1.importance - p2.importance);
  cost += config_.w_importance * i_diff;

  return cost;
}

std::vector<std::pair<size_t, size_t>>
SalientPointMatcher::match(const std::vector<SalientPoint> &s1,
                           const std::vector<SalientPoint> &s2) {

  size_t n = s1.size();
  size_t m = s2.size();

  if (n == 0 || m == 0)
    return {};

  // DP table: dp[i][j] = min cost to match prefix s1[0..i-1] and s2[0..j-1]
  std::vector<std::vector<double>> dp(
      n + 1,
      std::vector<double>(m + 1, std::numeric_limits<double>::infinity()));

  // Direction table for traceback: 0=Match, 1=SkipS1(Up), 2=SkipS2(Left)
  std::vector<std::vector<int>> dir(n + 1, std::vector<int>(m + 1, -1));

  // Initialization
  // Force S1[0] matches S2[0]
  // We effectively say that the state (0,0) costs 0 to start,
  // BUT the transition to (1,1) MUST happen.
  // Actually, standard DP allows:
  // dp[0][0] = 0;
  // To force start match, we make sure dp[1][0] and dp[0][1] are INF (already
  // done). And dp[1][1] will be computed as dp[0][0] + cost(0,0). Skips are
  // allowed AFTER the first match.

  dp[0][0] = 0.0;

  // Fill DP
  for (size_t i = 1; i <= n; ++i) {
    for (size_t j = 1; j <= m; ++j) {
      // Cost to match s1[i-1] and s2[j-1]
      double match_cost = compute_cost(s1[i - 1], s2[j - 1]);
      double c_match = dp[i - 1][j - 1] + match_cost;

      // Cost to skip s1[i-1]
      // Determine skip cost - maybe lower for low importance points?
      // For now constant from config
      double skip_s1_cost = dp[i - 1][j] + config_.skip_cost;

      // Cost to skip s2[j-1]
      double skip_s2_cost = dp[i][j - 1] + config_.skip_cost;

      // Enforce start match constraint specifically:
      // We cannot skip index 0. i.e., s1[0] and s2[0] MUST match.
      // Index 1 in DP corresponds to index 0 in vector.
      // So if i=1, we MUST come from diagonal (0,0) -> match.
      // If we attempt skip_s1 (state i-1, j), it would mean coming from (0, 1)
      // which is INF. So implicit INF in initialization handles the start
      // constraint.

      // Select min
      if (c_match <= skip_s1_cost && c_match <= skip_s2_cost) {
        dp[i][j] = c_match;
        dir[i][j] = 0; // Match
      } else if (skip_s1_cost <= skip_s2_cost) {
        dp[i][j] = skip_s1_cost;
        dir[i][j] = 1; // Skip S1
      } else {
        dp[i][j] = skip_s2_cost;
        dir[i][j] = 2; // Skip S2
      }
    }
  }

  // Traceback
  std::vector<std::pair<size_t, size_t>> matches;
  size_t i = n;
  size_t j = m;

  // Force end match?
  // Often desirable to force s1[n-1] matches s2[m-1].
  // If we force end match, we assume the path ends at (n, m) coming from
  // diagonal? Not necessarily diagonal, but we must "consume" both to the end.
  // The DP state (n, m) is the cost to consume all.
  // We just trace back from (n, m).

  while (i > 0 && j > 0) {
    if (dir[i][j] == 0) {
      matches.emplace_back(i - 1, j - 1);
      i--;
      j--;
    } else if (dir[i][j] == 1) {
      // Skip S1[i-1]
      i--;
    } else {
      // Skip S2[j-1]
      j--;
    }
  }

  // If strict endpoint matching is desired, we should check if (0,0) was added
  // (It should be due to INF boundaries).

  std::reverse(matches.begin(), matches.end());
  return matches;
}

} // namespace ftpsc
