/**
 * @file similarity_transform.cpp
 * @brief Implementation of optimal similarity transformation
 *
 * Implements the matching degree function for FTP-SC using:
 * - Parameter merging (Yang-Feng 2009 Section 3.2.1)
 * - Cohen-Guibas optimal similarity transform
 * - Analytical cost formula (Yang-Feng Appendix A)
 *
 * References:
 * - Cohen & Guibas 1997: "Shape-Based Similarity"
 * - Yang & Feng 2009: "2D shape morphing..." Appendix A
 * - FTP-SC: Section 3.2
 */

#include "similarity_transform.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <numeric>

namespace ftpsc {

namespace {

/**
 * @brief Compute centroid of a point set
 */
Vec2 compute_centroid(const std::vector<Vec2> &points) {
  if (points.empty()) {
    return Vec2(0.0, 0.0);
  }

  double sum_x = 0.0;
  double sum_y = 0.0;

  for (const auto &p : points) {
    sum_x += p.x;
    sum_y += p.y;
  }

  return Vec2(sum_x / points.size(), sum_y / points.size());
}

/**
 * @brief Compute arc-length parameterization for a stroke
 *
 * Returns cumulative arc lengths [0, L1, L2, ..., L_total]
 * where L_i is the total length up to point i.
 */
std::vector<double> compute_arc_lengths(const Stroke &stroke) {
  std::vector<double> arc_lengths;
  arc_lengths.reserve(stroke.points.size());
  arc_lengths.push_back(0.0); // First point at t=0

  double cumulative = 0.0;
  for (size_t i = 1; i < stroke.points.size(); ++i) {
    double dx = stroke.points[i].x - stroke.points[i - 1].x;
    double dy = stroke.points[i].y - stroke.points[i - 1].y;
    double segment_length = std::sqrt(dx * dx + dy * dy);
    cumulative += segment_length;
    arc_lengths.push_back(cumulative);
  }

  return arc_lengths;
}

/**
 * @brief Resample stroke to specific parameter values using linear
 * interpolation
 *
 * @param stroke Input stroke
 * @param arc_lengths Arc-length parameters of input stroke
 * @param target_params Target parameter values to sample at
 * @return Resampled stroke points
 */
std::vector<Vec2> resample_stroke(const Stroke &stroke,
                                  const std::vector<double> &arc_lengths,
                                  const std::vector<double> &target_params) {
  std::vector<Vec2> resampled;
  resampled.reserve(target_params.size());

  double total_length = arc_lengths.back();

  for (double t : target_params) {
    // Clamp t to [0, total_length]
    t = std::max(0.0, std::min(t, total_length));

    // Find segment containing this parameter value
    // Binary search would be faster, but linear is fine for moderate sizes
    size_t i = 0;
    while (i + 1 < arc_lengths.size() && arc_lengths[i + 1] < t) {
      ++i;
    }

    // Handle edge cases
    if (i + 1 >= stroke.points.size()) {
      resampled.push_back(stroke.points.back());
      continue;
    }

    // Linear interpolation within segment
    double t0 = arc_lengths[i];
    double t1 = arc_lengths[i + 1];
    double segment_length = t1 - t0;

    if (segment_length < 1e-10) {
      // Degenerate segment
      resampled.push_back(stroke.points[i]);
    } else {
      double alpha = (t - t0) / segment_length;
      Vec2 p0 = stroke.points[i];
      Vec2 p1 = stroke.points[i + 1];

      Vec2 interpolated(p0.x + alpha * (p1.x - p0.x),
                        p0.y + alpha * (p1.y - p0.y));
      resampled.push_back(interpolated);
    }
  }

  return resampled;
}

/**
 * @brief Merge parameters from two strokes (Yang-Feng 2009 Section 3.2.1)
 *
 * Creates a unified parameter set by merging arc-length parameters
 * from both strokes, normalized to [0, 1].
 */
std::vector<double> merge_parameters(const std::vector<double> &params1,
                                     const std::vector<double> &params2) {
  // Normalize both parameter sets to [0, 1]
  std::vector<double> norm1, norm2;
  double max1 = params1.empty() ? 1.0 : params1.back();
  double max2 = params2.empty() ? 1.0 : params2.back();

  if (max1 < 1e-10)
    max1 = 1.0; // Avoid division by zero
  if (max2 < 1e-10)
    max2 = 1.0;

  for (double p : params1) {
    norm1.push_back(p / max1);
  }
  for (double p : params2) {
    norm2.push_back(p / max2);
  }

  // Merge and sort
  std::vector<double> merged;
  merged.reserve(norm1.size() + norm2.size());
  merged.insert(merged.end(), norm1.begin(), norm1.end());
  merged.insert(merged.end(), norm2.begin(), norm2.end());

  std::sort(merged.begin(), merged.end());

  // Remove duplicates (within epsilon)
  const double epsilon = 1e-6;
  auto new_end =
      std::unique(merged.begin(), merged.end(), [epsilon](double a, double b) {
        return std::abs(a - b) < epsilon;
      });
  merged.erase(new_end, merged.end());

  return merged;
}

} // anonymous namespace

// =============================================================================
// Public API Implementation
// =============================================================================

SimilarityTransform
find_optimal_similarity_transform_2d(const std::vector<Vec2> &points1,
                                     const std::vector<Vec2> &points2) {

  assert(points1.size() == points2.size() && "Point sets must have same size");
  assert(!points1.empty() && "Point sets cannot be empty");

  // Step 1: Compute centroids
  Vec2 c1 = compute_centroid(points1);
  Vec2 c2 = compute_centroid(points2);

  // Step 2: Center the point sets
  std::vector<Vec2> centered1, centered2;
  centered1.reserve(points1.size());
  centered2.reserve(points2.size());

  for (const auto &p : points1) {
    centered1.push_back(Vec2(p.x - c1.x, p.y - c1.y));
  }
  for (const auto &p : points2) {
    centered2.push_back(Vec2(p.x - c2.x, p.y - c2.y));
  }

  // Step 3: Compute cross-covariance matrix H
  // H = Σ(p1_i × p2_i^T) for 2D: H = [Sxx Sxy; Syx Syy]
  double Sxx = 0.0, Sxy = 0.0, Syx = 0.0, Syy = 0.0;

  for (size_t i = 0; i < centered1.size(); ++i) {
    Sxx += centered1[i].x * centered2[i].x;
    Sxy += centered1[i].x * centered2[i].y;
    Syx += centered1[i].y * centered2[i].x;
    Syy += centered1[i].y * centered2[i].y;
  }

  // Step 4: Compute rotation angle using atan2
  // From Horn 1987: θ = atan2(Sxy - Syx, Sxx + Syy)
  double rotation = std::atan2(Sxy - Syx, Sxx + Syy);

  // Step 5: Compute scale as ratio of moments
  double scale = 1.0;

  // Moment of centered points2 (target)
  double moment2 = 0.0;
  for (const auto &p : centered2) {
    moment2 += p.x * p.x + p.y * p.y;
  }

  // Moment of centered points1 (source) after rotation
  double cos_r = std::cos(rotation);
  double sin_r = std::sin(rotation);
  double moment1_rotated = 0.0;

  for (const auto &p : centered1) {
    double rx = p.x * cos_r - p.y * sin_r;
    double ry = p.x * sin_r + p.y * cos_r;
    moment1_rotated += rx * rx + ry * ry;
  }

  if (moment1_rotated > 1e-10) {
    scale = std::sqrt(moment2 / moment1_rotated);
  }

  // Step 6: Compute translation
  // t = c2 - scale * Rot(c1)
  double c1_rotated_x = c1.x * cos_r - c1.y * sin_r;
  double c1_rotated_y = c1.x * sin_r + c1.y * cos_r;

  Vec2 translation(c2.x - scale * c1_rotated_x, c2.y - scale * c1_rotated_y);

  return SimilarityTransform(scale, rotation, translation);
}

SimilarityTransform find_optimal_similarity_transform(const Stroke &stroke1,
                                                      const Stroke &stroke2) {

  assert(stroke1.points.size() == stroke2.points.size() &&
         "Strokes must have same number of points after resampling");

  return find_optimal_similarity_transform_2d(stroke1.points, stroke2.points);
}

double compute_shape_difference(const Stroke &aligned_stroke1,
                                const Stroke &stroke2,
                                const std::vector<double> &arc_params) {
  assert(aligned_stroke1.points.size() == stroke2.points.size());
  assert(arc_params.size() == stroke2.points.size());

  // Compute integral: √(∫|f₁(t)˜ - f₂(t)|² dt)
  // Using trapezoidal rule for numerical integration

  double sum = 0.0;

  for (size_t i = 1; i < aligned_stroke1.points.size(); ++i) {
    // Distance at this point
    double dx1 = aligned_stroke1.points[i - 1].x - stroke2.points[i - 1].x;
    double dy1 = aligned_stroke1.points[i - 1].y - stroke2.points[i - 1].y;
    double dist_sq1 = dx1 * dx1 + dy1 * dy1;

    double dx2 = aligned_stroke1.points[i].x - stroke2.points[i].x;
    double dy2 = aligned_stroke1.points[i].y - stroke2.points[i].y;
    double dist_sq2 = dx2 * dx2 + dy2 * dy2;

    // Trapezoidal rule: (f(i-1) + f(i)) / 2 * dt
    double dt = arc_params[i] - arc_params[i - 1];
    sum += (dist_sq1 + dist_sq2) * 0.5 * dt;
  }

  return std::sqrt(sum);
}

double compute_matching_degree(const Stroke &stroke1, const Stroke &stroke2) {
  // Handle trivial cases
  if (stroke1.points.empty() || stroke2.points.empty()) {
    return std::numeric_limits<double>::infinity();
  }

  if (stroke1.points.size() == 1 && stroke2.points.size() == 1) {
    // Single point strokes: just Euclidean distance
    return stroke1.points[0].distance_to(stroke2.points[0]);
  }

  // Step 1: Compute arc-length parameterizations
  std::vector<double> arc1 = compute_arc_lengths(stroke1);
  std::vector<double> arc2 = compute_arc_lengths(stroke2);

  // Step 2: Merge parameters (Yang-Feng Section 3.2.1)
  std::vector<double> merged_normalized = merge_parameters(arc1, arc2);

  // Step 3: Resample both strokes to common parameterization
  // Scale merged parameters back to stroke1's length for resampling
  double length1 = arc1.back();
  double length2 = arc2.back();

  std::vector<double> merged_params1, merged_params2;
  for (double t : merged_normalized) {
    merged_params1.push_back(t * length1);
    merged_params2.push_back(t * length2);
  }

  std::vector<Vec2> resampled1 = resample_stroke(stroke1, arc1, merged_params1);
  std::vector<Vec2> resampled2 = resample_stroke(stroke2, arc2, merged_params2);

  assert(resampled1.size() == resampled2.size());

  // Step 4: Find optimal similarity transformation (Cohen-Guibas)
  SimilarityTransform transform =
      find_optimal_similarity_transform_2d(resampled1, resampled2);

  // Step 5: Apply transformation to stroke1's resampled points
  std::vector<Vec2> aligned1;
  aligned1.reserve(resampled1.size());
  for (const auto &p : resampled1) {
    aligned1.push_back(transform.apply(p));
  }

  // Step 6: Compute shape difference (Yang-Feng Appendix A)
  // Create temporary stroke for aligned points
  Stroke aligned_stroke;
  aligned_stroke.points = aligned1;

  Stroke target_stroke;
  target_stroke.points = resampled2;

  double cost = compute_shape_difference(aligned_stroke, target_stroke,
                                         merged_normalized);

  return cost;
}

} // namespace ftpsc
