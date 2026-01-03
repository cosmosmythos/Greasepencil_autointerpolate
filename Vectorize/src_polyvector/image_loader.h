/**
 * Image loading utilities for PolyVector
 * Provides master-equivalent image preprocessing
 */
#pragma once

#include <opencv2/opencv.hpp>
#include <string>

namespace polyvector {

/**
 * Load and preprocess image exactly like PolyVectorization master
 * 
 * This function replicates master's preprocessing:
 * 1. Load image (BGR or BGRA)
 * 2. Handle alpha by compositing on white if present
 * 3. Convert to grayscale
 * 4. Return as CV_8UC1 (single-channel uint8)
 * 
 * @param filepath Path to image file (supports PNG, JPG, etc.)
 * @param handle_alpha If true, composite RGBA on white background
 * @return Grayscale image (CV_8UC1), empty on failure
 */
cv::Mat load_image_like_master(const std::string& filepath, bool handle_alpha = true);

} // namespace polyvector
