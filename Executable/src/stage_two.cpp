/**
 * @file stage_two.cpp
 * @brief Implementation of Stage 2 (Neighborhood Competition) components
 */

#define _USE_MATH_DEFINES
#include "fuzzy_topology.h"
#include "similarity_transform.h"
#include "stroke_matcher.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>

#ifdef FTPSC_USE_EIGEN
#include <Eigen/Dense>
#endif

#ifdef FTPSC_USE_NANOFLANN
#include <nanoflann.hpp>
#endif

namespace ftpsc {

namespace {

#ifdef FTPSC_USE_NANOFLANN
// Helper: Adapter for nanoflann to work with our stroke centroids
struct StrokeCentroidAdapter {
  const std::vector<Stroke> *strokes;
  
  StrokeCentroidAdapter(const std::vector<Stroke> &s) : strokes(&s) {}
  
  // Must return the number of data points
  inline size_t kdtree_get_point_count() const { return strokes->size(); }
  
  // Returns the dim'th component of the idx'th point
  inline double kdtree_get_pt(const size_t idx, const size_t dim) const {
    Vec2 centroid = (*strokes)[idx].get_centroid();
    return (dim == 0) ? centroid.x : centroid.y;
  }
  
  // Optional bounding-box computation
  template <class BBOX> bool kdtree_get_bbox(BBOX &) const { return false; }
};

// KD-tree typedef
typedef nanoflann::KDTreeSingleIndexAdaptor<
    nanoflann::L2_Simple_Adaptor<double, StrokeCentroidAdapter>,
    StrokeCentroidAdapter,
    2 /* dimensions */
> StrokeKDTree;
#endif

// Helper: Calculate centroid of a stroke
Vec2 get_stroke_centroid(const Stroke &s) {
  if (s.points.empty())
    return Vec2(0, 0);
  return s.get_centroid();
}

// Helper: Get k-nearest neighbors using nanoflann k-d tree (fast) or brute force (fallback)
std::vector<int> get_k_nearest_neighbors(const Stroke &center,
                                         const std::vector<Stroke> &all_strokes,
                                         int k, int center_idx,
                                         const Correspondence &corr,
                                         bool is_target) {

#ifdef FTPSC_USE_NANOFLANN
  // Fast k-d tree search (O(log n) per query)
  
  // Build k-d tree from stroke centroids
  StrokeCentroidAdapter adapter(all_strokes);
  StrokeKDTree tree(2 /* dim */, adapter, nanoflann::KDTreeSingleIndexAdaptorParams(10 /* max leaf */));
  tree.buildIndex();
  
  Vec2 query_point = center.get_centroid();
  double query_pt[2] = {query_point.x, query_point.y};
  
  // Query for more neighbors than needed (we'll filter out matched ones)
  size_t num_results = std::min(k * 3, static_cast<int>(all_strokes.size()));
  std::vector<size_t> ret_indexes(num_results);
  std::vector<double> out_dists_sqr(num_results);
  
  nanoflann::KNNResultSet<double> resultSet(num_results);
  resultSet.init(&ret_indexes[0], &out_dists_sqr[0]);
  tree.findNeighbors(resultSet, &query_pt[0]);
  
  // Filter results: exclude self and already-matched strokes
  std::vector<int> result;
  for (size_t i = 0; i < resultSet.size(); ++i) {
    int idx = static_cast<int>(ret_indexes[i]);
    
    if (idx == center_idx)
      continue; // Skip self
    
    // Skip if already matched
    if (is_target) {
      if (corr.is_matched_target(idx))
        continue;
    } else {
      if (corr.is_matched_initial(idx))
        continue;
    }
    
    result.push_back(idx);
    
    if (result.size() >= static_cast<size_t>(k))
      break;
  }
  
  return result;

#else
  // Fallback: Brute force O(n) search
  
  struct Neighbor {
    int idx;
    double dist;
    bool operator<(const Neighbor &other) const { return dist < other.dist; }
  };

  std::vector<Neighbor> neighbors;
  neighbors.reserve(all_strokes.size());

  Vec2 c_center = get_stroke_centroid(center);

  for (size_t i = 0; i < all_strokes.size(); ++i) {
    if (i == static_cast<size_t>(center_idx))
      continue;

    // Skip if already matched
    if (is_target) {
      if (corr.is_matched_target(i))
        continue;
    } else {
      if (corr.is_matched_initial(i))
        continue;
    }

    // Use centroid-to-centroid distance for k-NN (consistent with k-d tree)
    Vec2 other_centroid = all_strokes[i].get_centroid();
    double dist = (c_center - other_centroid).length();

    neighbors.push_back({static_cast<int>(i), dist});
  }

  // Sort and take top k
  std::sort(neighbors.begin(), neighbors.end());
  if (neighbors.size() > static_cast<size_t>(k)) {
    neighbors.resize(k);
  }

  std::vector<int> result;
  for (const auto &n : neighbors) {
    result.push_back(n.idx);
  }
  return result;
#endif
}

#ifdef FTPSC_USE_EIGEN
// Helper: Compute PCA-based local coordinate system for a stroke
// Returns (origin, x_axis, y_axis) where axes are unit vectors
struct LocalCoordinateSystem {
  Vec2 origin;       // Centroid of reference stroke
  Vec2 x_axis;       // Principal component (major direction)
  Vec2 y_axis;       // Perpendicular to x_axis
  bool valid = false;
};

LocalCoordinateSystem compute_local_coords(const Stroke &reference) {
  LocalCoordinateSystem lcs;
  
  if (reference.points.size() < 2) {
    return lcs; // Invalid
  }

  // 1. Center = stroke centroid
  lcs.origin = reference.get_centroid();

  // 2. Build covariance matrix from stroke points
  Eigen::MatrixXd points(reference.points.size(), 2);
  for (size_t i = 0; i < reference.points.size(); ++i) {
    points(i, 0) = reference.points[i].x - lcs.origin.x;
    points(i, 1) = reference.points[i].y - lcs.origin.y;
  }

  // 3. Compute covariance
  Eigen::Matrix2d cov = (points.transpose() * points) / static_cast<double>(points.rows() - 1);

  // 4. Eigen decomposition
  Eigen::SelfAdjointEigenSolver<Eigen::Matrix2d> solver(cov);
  if (solver.info() != Eigen::Success) {
    return lcs; // Failed
  }

  // 5. Extract principal eigenvector (largest eigenvalue = col 1)
  Eigen::Vector2d major_eigenvector = solver.eigenvectors().col(1);
  
  lcs.x_axis = Vec2(major_eigenvector(0), major_eigenvector(1));
  lcs.y_axis = Vec2(-lcs.x_axis.y, lcs.x_axis.x); // Perpendicular (rotated 90° CCW)
  lcs.valid = true;

  return lcs;
}

// Helper: Transform a point from global to local coordinate system
Vec2 to_local_coords(const Vec2 &global_point, const LocalCoordinateSystem &lcs) {
  Vec2 relative = global_point - lcs.origin;
  double x_local = relative.x * lcs.x_axis.x + relative.y * lcs.x_axis.y;
  double y_local = relative.x * lcs.y_axis.x + relative.y * lcs.y_axis.y;
  return Vec2(x_local, y_local);
}
#endif

// Helper: Calculate Stage 2 pairwise cost using PCA local coordinates
// Paper Section 3.4: "We use PCA to extract local coordinate systems"
double compute_stage_two_cost(const Stroke &S, const Stroke &Si,
                              const Stroke &T, const Stroke &Tj,
                              double angle_threshold) {

  // 1. Shape matching cost (Standard Stage 1 cost)
  double shape_cost = compute_matching_degree(Si, Tj);

#ifdef FTPSC_USE_EIGEN
  // 2. PCA-based structural cost (Paper Section 3.4)
  
  // Build local coordinate systems for matched seed strokes S and T
  LocalCoordinateSystem lcs_S = compute_local_coords(S);
  LocalCoordinateSystem lcs_T = compute_local_coords(T);

  if (!lcs_S.valid || !lcs_T.valid) {
    // Fallback to simple centroid-based cost
    Vec2 c_Si = Si.get_centroid();
    Vec2 c_Tj = Tj.get_centroid();
    Vec2 c_S = S.get_centroid();
    Vec2 c_T = T.get_centroid();
    
    double dist_diff = std::abs((c_Si - c_S).length() - (c_Tj - c_T).length());
    return shape_cost + dist_diff * 0.5;
  }

  // Transform neighbor centroids into local coordinate systems
  Vec2 c_Si = Si.get_centroid();
  Vec2 c_Tj = Tj.get_centroid();
  
  Vec2 local_Si = to_local_coords(c_Si, lcs_S);
  Vec2 local_Tj = to_local_coords(c_Tj, lcs_T);

  // 3. Compare relative positions in local coordinates
  // Distance between relative positions
  Vec2 position_diff = local_Si - local_Tj;
  double position_distance = position_diff.length();

  // 4. Angle threshold check (hard constraint from paper)
  // "If the angle difference exceeds π/4, we discard the candidate"
  double angle_diff = 0.0;
  if (local_Si.length_squared() > 1e-6 && local_Tj.length_squared() > 1e-6) {
    double angle_Si = std::atan2(local_Si.y, local_Si.x);
    double angle_Tj = std::atan2(local_Tj.y, local_Tj.x);
    angle_diff = std::abs(angle_Si - angle_Tj);
    
    // Normalize to [0, π]
    while (angle_diff > M_PI)
      angle_diff -= 2 * M_PI;
    angle_diff = std::abs(angle_diff);
    
    // Hard threshold: if angle difference too large, return very high cost
    if (angle_diff > angle_threshold) {
      return 1e6; // Very high cost to reject this candidate
    }
  }

  // Weights for final cost
  double w_shape = 1.0;
  double w_position = 0.3;
  double w_angle = 0.2;

  return w_shape * shape_cost + w_position * position_distance + w_angle * angle_diff;

#else
  // Fallback: simplified cost without PCA (if Eigen not available)
  Vec2 c_S = S.get_centroid();
  Vec2 c_Si = Si.get_centroid();
  Vec2 c_T = T.get_centroid();
  Vec2 c_Tj = Tj.get_centroid();

  Vec2 v_S_Si = c_Si - c_S;
  Vec2 v_T_Tj = c_Tj - c_T;

  double angle_diff = 0.0;
  if (v_S_Si.length_squared() > 1e-6 && v_T_Tj.length_squared() > 1e-6) {
    double angle1 = std::atan2(v_S_Si.y, v_S_Si.x);
    double angle2 = std::atan2(v_T_Tj.y, v_T_Tj.x);
    angle_diff = std::abs(angle1 - angle2);
    while (angle_diff > M_PI)
      angle_diff -= 2 * M_PI;
    angle_diff = std::abs(angle_diff);
    
    if (angle_diff > angle_threshold) {
      return 1e6;
    }
  }

  double dist_diff = std::abs(v_S_Si.length() - v_T_Tj.length());
  return shape_cost + dist_diff * 0.5 + angle_diff * 0.5;
#endif
}

} // namespace

// =============================================================================
// Stage 2: SI Component (Seed Initialization)
// =============================================================================

std::vector<CandidatePair> StrokeMatcher::stage_two_si_component(
    const std::vector<Stroke> &initial_strokes,
    const std::vector<Stroke> &target_strokes,
    const Correspondence &stage_one_result,
    const Correspondence &current_correspondence) {

  // "All the correspondences found in stage one are used as seeds."
  std::vector<CandidatePair> seeds;

  // Re-pack existing correspondence into seeds
  for (const auto &match : stage_one_result.matches) {
    // We technically don't need to re-compute cost if we stored it,
    // but for SI interface we need to return CandidatePair.
    // We can just use dummy cost or 0, as they are already matched.
    // Wait, Greedy Matcher will try to add them.
    // It's fine.
    seeds.emplace_back(match.first, match.second, 0.0);
  }

  return seeds;
}

// =============================================================================
// Stage 2: CD Component (Candidate Derivation)
// =============================================================================

std::vector<CandidatePair> StrokeMatcher::stage_two_cd_component(
    const CandidatePair &seed, const std::vector<Stroke> &initial_strokes,
    const std::vector<Stroke> &target_strokes,
    const Correspondence &current_correspondence) {

  std::vector<CandidatePair> candidates;

  // Seed (S, T) matches
  int s_idx = seed.initial_index;
  int t_idx = seed.target_index;
  const Stroke &S = initial_strokes[s_idx];
  const Stroke &T = target_strokes[t_idx];

  // Find k-nearest unmatched neighbors for S
  std::vector<int> neighbors_S =
      get_k_nearest_neighbors(S, initial_strokes, config_.k_neighbors, s_idx,
                              current_correspondence, false);

  // Find k-nearest unmatched neighbors for T
  std::vector<int> neighbors_T =
      get_k_nearest_neighbors(T, target_strokes, config_.k_neighbors, t_idx,
                              current_correspondence, true);

  // Form pairwise candidates between neighbors
  // Paper: "pair each neighbor of S with each neighbor of T" (implied
  // all-to-all in valid region?) Actually, we want to find best matches.

  for (int si_idx : neighbors_S) {
    for (int tj_idx : neighbors_T) {

      // Compute cost with PCA local coordinates and angle threshold
      double cost = compute_stage_two_cost(S, initial_strokes[si_idx], T,
                                           target_strokes[tj_idx],
                                           config_.angle_threshold);

      // Skip if cost is too high (angle threshold exceeded)
      if (cost >= 1e5) {
        continue; // Discard this candidate
      }

      // Note: cost is "lower is better". CandidatePair needs "matching degree"
      // (higher is better).
      candidates.emplace_back(si_idx, tj_idx, -cost);
    }
  }

  return candidates;
}

// =============================================================================
// Stage 2: Runner
// =============================================================================

Correspondence
StrokeMatcher::run_stage_two(const std::vector<Stroke> &initial_strokes,
                             const std::vector<Stroke> &target_strokes,
                             const Correspondence &stage_one_result) {

  GreedyMatcher matcher;

  using namespace std::placeholders;

  // Bind member functions
  // Note: stage_two_si_component needs extra argument stage_one_result?
  // The Generic SI signature is (init, target, current).
  // My member func has (init, target, stage1, current).
  // So I bind stage1_result here.

  auto si = std::bind(&StrokeMatcher::stage_two_si_component, this, _1, _2,
                      stage_one_result, _3);
  auto cd =
      std::bind(&StrokeMatcher::stage_two_cd_component, this, _1, _2, _3, _4);

  // We pass stage_one_result as 'existing_correspondence' to the matcher
  return matcher.match(initial_strokes, target_strokes, si, cd,
                       stage_one_result);
}

} // namespace ftpsc
