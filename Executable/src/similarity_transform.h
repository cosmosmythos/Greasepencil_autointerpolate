/**
 * @file similarity_transform.h
 * @brief Optimal similarity transformation (Cohen & Guibas 1997)
 *
 * Implements the analytical solution for finding the optimal similarity
 * transformation (translation, rotation, uniform scaling) between two
 * point sets, as referenced in the FTP-SC paper.
 *
 * References:
 * - Cohen & Guibas 1997: "Shape-Based Similarity"
 * - Yang & Feng 2009: Appendix A (closed-form solution)
 */

#pragma once

#include "stroke.h"
#include <array>

namespace ftpsc {

/**
 * @brief A 2D similarity transformation: scale, rotation, translation
 *
 * Transforms a point p as: p' = scale * Rotate(p, theta) + translation
 */
struct SimilarityTransform {
  double scale;     // λ (lambda) - uniform scaling factor
  double rotation;  // θ (theta) - rotation angle in radians
  Vec2 translation; // (tx, ty) - translation vector

  SimilarityTransform() : scale(1.0), rotation(0.0), translation(0.0, 0.0) {}

  SimilarityTransform(double s, double r, Vec2 t)
      : scale(s), rotation(r), translation(t) {}

  /**
   * @brief Apply transformation to a single point
   * @param p Input point
   * @return Transformed point: scale * Rot(p) + trans
   */
  Vec2 apply(const Vec2 &p) const {
    double cos_theta = std::cos(rotation);
    double sin_theta = std::sin(rotation);

    // Rotation matrix application
    double rx = p.x * cos_theta - p.y * sin_theta;
    double ry = p.x * sin_theta + p.y * cos_theta;

    // Scale and translate
    return Vec2(scale * rx + translation.x, scale * ry + translation.y);
  }

  /**
   * @brief Apply transformation to entire stroke
   * @param stroke Input stroke
   * @return New transformed stroke
   */
  Stroke apply(const Stroke &stroke) const {
    Stroke result;
    result.points.reserve(stroke.points.size());

    for (const auto &p : stroke.points) {
      result.points.push_back(apply(p));
    }

    return result;
  }
};

/**
 * @brief Find optimal similarity transformation between two strokes
 *
 * This implements the Cohen & Guibas 1997 method referenced in FTP-SC.
 * The transformation is computed to minimize the mean squared error
 * between corresponding points.
 *
 * IMPORTANT: Both strokes must have the same number of points and
 * corresponding points must be at the same indices. This is typically
 * achieved by resampling both strokes to a common parameterization.
 *
 * @param stroke1 Source stroke (will be transformed)
 * @param stroke2 Target stroke
 * @return Optimal similarity transformation
 *
 * Mathematical details:
 * - Centers both point sets
 * - Computes cross-covariance matrix H = Σ(p1ᵢ ⊗ p2ᵢ)
 * - Extracts rotation via SVD: R = V * U^T
 * - Computes scale as ratio of moments
 * - Derives translation to align centroids
 */
SimilarityTransform find_optimal_similarity_transform(const Stroke &stroke1,
                                                      const Stroke &stroke2);

/**
 * @brief Simplified 2D case using direct formula
 *
 * For 2D points, we can avoid full SVD and use a simpler formula
 * based on atan2. This is faster and numerically stable for 2D.
 *
 * From Horn 1987 "Closed-form solution of absolute orientation"
 */
SimilarityTransform
find_optimal_similarity_transform_2d(const std::vector<Vec2> &points1,
                                     const std::vector<Vec2> &points2);

/**
 * @brief Compute shape difference after optimal alignment
 *
 * This is the visual similarity v(f₁, f₂) from Yang & Feng 2009.
 * After finding the optimal alignment, this computes the residual
 * distance as the "matching degree" between strokes.
 *
 * Formula from paper:
 * v(f₁, f₂) = √(∫|f₁(t)Ã - f₂(t)|² dt)
 *
 * Where Ã is the optimal similarity transform.
 *
 * @param aligned_stroke1 Stroke 1 after applying optimal transform
 * @param stroke2 Target stroke (unchanged)
 * @param arc_params Arc-length parameters for integration
 * @return Shape difference (lower = more similar)
 */
double compute_shape_difference(const Stroke &aligned_stroke1,
                                const Stroke &stroke2,
                                const std::vector<double> &arc_params);

/**
 * @brief All-in-one: Find transform and compute matching degree
 *
 * This is the complete "matching degree" function referenced in FTP-SC.
 * It combines:
 * 1. Stroke parameterization (merge parameters)
 * 2. Resampling to common parameters
 * 3. Optimal similarity transform (Cohen-Guibas)
 * 4. Shape difference computation (Yang-Feng Appendix A)
 *
 * @param stroke1 First stroke
 * @param stroke2 Second stroke
 * @return Matching cost (lower = better match)
 */
double compute_matching_degree(const Stroke &stroke1, const Stroke &stroke2);

} // namespace ftpsc
