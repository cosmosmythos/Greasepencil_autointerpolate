#ifndef POLYVECTOR_CORE_H
#define POLYVECTOR_CORE_H

#include <vector>
#include <string>
#include <Eigen/Dense>
#include <opencv2/core/core.hpp>

// Forward declarations
namespace polyvector {

/**
 * Main vectorization function that processes an image and returns polylines
 * 
 * @param image_path Path to input image file
 * @param threshold Background/foreground threshold (0-255), default 90
 * @param verbose Enable verbose logging for debugging, default false
 * @return Vector of polylines, each polyline is a vector of (x,y) points
 */
std::vector<std::vector<std::pair<double, double>>> 
vectorize_image(const std::string& image_path,
                double threshold = 90.0,
                bool verbose = false);

/**
 * Process image from OpenCV Mat directly
 * 
 * @param input_image OpenCV Mat (grayscale or color)
 * @param threshold Background/foreground threshold (0-255)
 * @param blur_pixels Gaussian blur kernel size (0-10), default 0 (no blur)
 * @param verbose Enable verbose logging for debugging, default false
 * @return Vector of polylines
 * 
 * Note: Smoothing (10 iters, 0.5 weight) and simplification (1e-2) 
 *       are hardcoded to match master exactly.
 */
std::vector<std::vector<std::pair<double, double>>> 
vectorize_mat(const cv::Mat& input_image,
              double threshold = 90.0,
              int blur_pixels = 0,
              bool verbose = false);

/**
 * Vectorize image file with smart downscaling for performance.
 * 
 * Automatically resizes large images before vectorization, then scales
 * the resulting polylines back to original image coordinates.
 * 
 * Downscaling logic:
 * 1. If max(width, height) > 1024, scale down to 1024 on longest side
 * 2. Further divide by user_downscale (1-4)
 * 3. Vectorize at reduced resolution
 * 4. Scale polyline coordinates back to original size
 * 
 * For small images (<= 1024px), downscaling is skipped unless user_downscale > 1.
 * 
 * @param image_path Path to input image file
 * @param threshold Background/foreground threshold (0-255), default 90
 * @param blur_pixels Gaussian blur radius (0-10), default 0
 * @param user_downscale Additional downscale divisor (1-4), default 1
 * @param verbose Enable verbose logging for debugging, default false
 * @return Vector of polylines in original image coordinate space
 */
std::vector<std::vector<std::pair<double, double>>> 
vectorize_image_with_downscale(const std::string& image_path,
                                double threshold = 90.0,
                                int blur_pixels = 0,
                                int user_downscale = 1,
                                bool verbose = false);

} // namespace polyvector

#endif // POLYVECTOR_CORE_H
