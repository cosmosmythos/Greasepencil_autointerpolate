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
 * @return Vector of polylines, each polyline is a vector of (x,y) points
 */
std::vector<std::vector<std::pair<double, double>>> 
vectorize_image(const std::string& image_path,
                double threshold = 90.0,
                int smooth_steps = 10,
                double smooth_weight = 0.5);

/**
 * Process image from OpenCV Mat directly
 * 
 * @param input_image OpenCV Mat (grayscale or color)
 * @param threshold Background/foreground threshold (0-255)
 * @return Vector of polylines
 */
std::vector<std::vector<std::pair<double, double>>> 
vectorize_mat(const cv::Mat& input_image,
              double threshold = 90.0,
              int smooth_steps = 10,
              double smooth_weight = 0.5);

} // namespace polyvector

#endif // POLYVECTOR_CORE_H
