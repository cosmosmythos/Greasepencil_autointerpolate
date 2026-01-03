/**
 * Image loading utilities for PolyVector
 * Provides master-equivalent image preprocessing
 */
#include "image_loader.h"
#include <iostream>

namespace polyvector {

cv::Mat load_image_like_master(const std::string& filepath, bool handle_alpha) {
    // Load image with unchanged flags to preserve alpha if present
    cv::Mat img = cv::imread(filepath, cv::IMREAD_UNCHANGED);
    
    if (img.empty()) {
        std::cerr << "Error: Failed to load image: " << filepath << std::endl;
        return cv::Mat();
    }
    
    cv::Mat bwImg;
    
    // Handle different channel formats
    if (img.channels() == 4 && handle_alpha) {
        // BGRA: Composite on white background
        // Master assumes opaque images; transparent PNGs should be composited
        
        std::vector<cv::Mat> channels;
        cv::split(img, channels);
        
        // channels[0] = B, channels[1] = G, channels[2] = R, channels[3] = Alpha
        cv::Mat bgr, alpha;
        cv::merge(std::vector<cv::Mat>{channels[0], channels[1], channels[2]}, bgr);
        alpha = channels[3];
        
        // Composite: result = bgr*alpha + white*(1-alpha)
        // Convert to float [0..1] for compositing
        cv::Mat bgr_f, alpha_f;
        bgr.convertTo(bgr_f, CV_32F, 1.0/255.0);
        alpha.convertTo(alpha_f, CV_32F, 1.0/255.0);
        
        // Expand alpha to 3 channels
        cv::Mat alpha_3ch;
        cv::merge(std::vector<cv::Mat>{alpha_f, alpha_f, alpha_f}, alpha_3ch);
        
        // Composite on white: result = bgr*alpha + 1*(1-alpha)
        cv::Mat composited = bgr_f.mul(alpha_3ch) + cv::Scalar(1.0, 1.0, 1.0) - alpha_3ch;
        
        // Convert back to uint8
        cv::Mat composited_8u;
        composited.convertTo(composited_8u, CV_8UC3, 255.0);
        
        // Convert to grayscale (BGR to GRAY)
        cv::cvtColor(composited_8u, bwImg, cv::COLOR_BGR2GRAY);
        
    } else if (img.channels() == 3) {
        // BGR: Convert directly to grayscale like master
        cv::cvtColor(img, bwImg, cv::COLOR_BGR2GRAY);
        
    } else if (img.channels() == 1) {
        // Already grayscale
        bwImg = img.clone();
        
    } else {
        std::cerr << "Error: Unsupported channel count: " << img.channels() << std::endl;
        return cv::Mat();
    }
    
    // Ensure we have CV_8UC1 (single-channel uint8)
    if (bwImg.type() != CV_8UC1) {
        bwImg.convertTo(bwImg, CV_8UC1);
    }
    
    return bwImg;
}

} // namespace polyvector
