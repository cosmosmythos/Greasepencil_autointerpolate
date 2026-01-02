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
 * @param smooth_steps Number of Laplacian smoothing iterations (0-20), default 10
 * @param smooth_weight Smoothing weight (0.0-1.0), default 0.5
 * @param simplify_epsilon Douglas-Peucker simplification tolerance (point reduction), default 0.01
 * @param verbose Enable verbose logging for debugging, default false
 * @return Vector of polylines, each polyline is a vector of (x,y) points
 */
std::vector<std::vector<std::pair<double, double>>> 
vectorize_image(const std::string& image_path,
                double threshold = 90.0,
                int smooth_steps = 10,
                double smooth_weight = 0.5,
                double simplify_epsilon = 0.01,
                bool verbose = false);

/**
 * Process image from OpenCV Mat directly
 * 
 * @param input_image OpenCV Mat (grayscale or color)
 * @param threshold Background/foreground threshold (0-255)
 * @param blur_pixels Gaussian blur kernel size (0-10), default 0 (no blur)
 * @param smooth_steps Number of Laplacian smoothing iterations (0-20), default 10
 * @param smooth_weight Smoothing weight (0.0-1.0), default 0.5
 * @param simplify_epsilon Douglas-Peucker simplification tolerance (point reduction), default 0.01
 * @param verbose Enable verbose logging for debugging, default false
 * @return Vector of polylines
 */
std::vector<std::vector<std::pair<double, double>>> 
vectorize_mat(const cv::Mat& input_image,
              double threshold = 90.0,
              int blur_pixels = 0,
              int smooth_steps = 10,
              double smooth_weight = 0.5,
              double simplify_epsilon = 0.01,
              bool verbose = false);

} // namespace polyvector

#endif // POLYVECTOR_CORE_H
