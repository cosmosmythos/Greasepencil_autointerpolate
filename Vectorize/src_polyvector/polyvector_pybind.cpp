/**
 * Python bindings for PolyVector line art vectorization
 * Using pybind11 for seamless numpy integration
 */

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include "polyvector_core.h"
#include "image_loader.h"
#include <opencv2/core/core.hpp>

namespace py = pybind11;

namespace polyvector {

/**
 * Convert numpy array to OpenCV Mat
 */
cv::Mat numpy_to_mat(py::array_t<uint8_t> input) {
    py::buffer_info buf = input.request();
    
    cv::Mat temp;
    if (buf.ndim == 2) {
        // Grayscale image (H, W)
        temp = cv::Mat(buf.shape[0], buf.shape[1], CV_8UC1, buf.ptr);
    } else if (buf.ndim == 3) {
        // Color image (H, W, C)
        if (buf.shape[2] == 3) {
            temp = cv::Mat(buf.shape[0], buf.shape[1], CV_8UC3, buf.ptr);
        } else if (buf.shape[2] == 4) {
            temp = cv::Mat(buf.shape[0], buf.shape[1], CV_8UC4, buf.ptr);
        } else {
            throw std::runtime_error("Unsupported image format. Expected (H,W) or (H,W,3) or (H,W,4)");
        }
    } else {
        throw std::runtime_error("Unsupported image format. Expected (H,W) or (H,W,3) or (H,W,4)");
    }
    
    // Clone the Mat so it owns its own memory (not backed by numpy array)
    // This prevents "locked type" errors when OpenCV tries to reallocate
    return temp.clone();
}

/**
 * Process numpy array directly
 */
std::vector<std::vector<std::pair<double, double>>> 
process_numpy(py::array_t<uint8_t> image,
              double threshold,
              int blur_pixels,
              bool verbose) {
    cv::Mat mat = numpy_to_mat(image);
    return vectorize_mat(mat, threshold, blur_pixels, verbose);
}

/**
 * Process image file using master-equivalent loading
 */
std::vector<std::vector<std::pair<double, double>>> 
process_file(const std::string& path,
             double threshold,
             int blur_pixels,
             bool verbose) {
    // Load image like master (handles RGBA compositing on white, converts to grayscale)
    cv::Mat bwImg = load_image_like_master(path, true);
    
    if (bwImg.empty()) {
        throw std::runtime_error("Failed to load image: " + path);
    }
    
    // Vectorize using core algorithm
    return vectorize_mat(bwImg, threshold, blur_pixels, verbose);
}

/**
 * Process image file with smart downscaling for performance
 */
std::vector<std::vector<std::pair<double, double>>> 
process_file_with_downscale(const std::string& path,
                             double threshold,
                             int blur_pixels,
                             int user_downscale,
                             bool verbose) {
    return vectorize_image_with_downscale(path, threshold, blur_pixels, user_downscale, verbose);
}

} // namespace polyvector

PYBIND11_MODULE(gp_linevector, m) {
    m.doc() = R"doc(
        GP LineVector - High-quality line art vectorization
        
        Based on PolyVector Fields algorithm (Bessmeltsev & Solomon 2019)
        
        Features:
        - Handles crossing lines (X-junctions) correctly
        - Preserves T-junctions 
        - Bridges gaps in sketchy lines
        - Produces clean, smooth vector output
    )doc";

    m.def("vectorize_image", &polyvector::process_file,
          py::arg("image_path"),
          py::arg("threshold") = 90.0,
          py::arg("blur_pixels") = 0,
          py::arg("verbose") = false,
          R"doc(
              Vectorize an image file (MASTER-EQUIVALENT METHOD).
              
              Loads image using OpenCV like PolyVectorization master does:
              - No Blender color management
              - RGBA composited on white background
              - Converted to grayscale with OpenCV weights
              - Then inverted, thresholded, and vectorized
              
              Args:
                  image_path: Path to input image (PNG, JPG, etc.)
                  threshold: Background/foreground threshold (0-255, default=90)
                             Lower values = more ink is detected
                  blur_pixels: Gaussian blur radius (0-10, default=0)
                  verbose: Enable detailed logging for debugging (default=False)
                             
              Returns:
                  List of polylines, each polyline is a list of (x, y) tuples
                  
              Example:
                  >>> import gp_linevector
                  >>> strokes = gp_linevector.vectorize_image("sketch.png")
                  >>> print(f"Found {len(strokes)} strokes")
          )doc");

    m.def("vectorize_image_downscale", &polyvector::process_file_with_downscale,
          py::arg("image_path"),
          py::arg("threshold") = 90.0,
          py::arg("blur_pixels") = 0,
          py::arg("user_downscale") = 1,
          py::arg("verbose") = false,
          R"doc(
              Vectorize an image file with smart downscaling for performance.
              
              Automatically resizes large images before vectorization, then scales
              the resulting polylines back to original image coordinates.
              
              Downscaling logic (all in C++/OpenCV):
              1. If max(width, height) > 1024, scale down to 1024 on longest side
              2. Further divide by user_downscale (1-4)
              3. Vectorize at reduced resolution using cv::resize with INTER_AREA
              4. Scale polyline coordinates back to original size
              
              For small images (<= 1024px), auto-cap is skipped unless user_downscale > 1.
              
              Args:
                  image_path: Path to input image (PNG, JPG, etc.)
                  threshold: Background/foreground threshold (0-255, default=90)
                  blur_pixels: Gaussian blur radius (0-10, default=0)
                  user_downscale: Additional downscale divisor (1-4, default=1)
                                  Higher = faster but less detail
                  verbose: Enable detailed logging for debugging (default=False)
                             
              Returns:
                  List of polylines in original image coordinate space
                  
              Example:
                  >>> import gp_linevector
                  >>> # Large image: auto-cap to 1024px, then divide by 2
                  >>> strokes = gp_linevector.vectorize_image_downscale("large.png", user_downscale=2)
                  >>> print(f"Found {len(strokes)} strokes")
          )doc");

    // DEPRECATED: vectorize_array (use vectorize_image for master-equivalent results)
    m.def("vectorize_array", &polyvector::process_numpy,
          py::arg("image"),
          py::arg("threshold") = 90.0,
          py::arg("blur_pixels") = 0,
          py::arg("verbose") = false,
          R"doc(
              Vectorize a numpy array image (DEPRECATED - use vectorize_image instead).
              
              WARNING: This method is subject to Blender's color management and pixel
              pipeline differences. For master-equivalent results, use vectorize_image()
              which loads files directly via OpenCV.
              
              Args:
                  image: Numpy array of shape (H, W) or (H, W, 3) or (H, W, 4)
                         dtype should be uint8
                  threshold: Background/foreground threshold (0-255, default=90)
                  blur_pixels: Gaussian blur preprocessing (0-10, default=0)
                              Helps clean up noisy images before vectorization
                  verbose: Enable detailed logging for debugging (default=False)
              
              Note:
                  Smoothing (10 iterations, weight 0.5) and simplification (epsilon 1e-2)
                  are hardcoded to exactly match PolyVectorization master.
                  
              Returns:
                  List of polylines, each polyline is a list of (x, y) tuples
                  
              Example:
                  >>> import gp_linevector
                  >>> import numpy as np
                  >>> from PIL import Image
                  >>> 
                  >>> img = np.array(Image.open("sketch.png"))
                  >>> strokes = gp_linevector.vectorize_array(img)
          )doc");
    
    // Version info
    m.attr("__version__") = "1.0.0";
    m.attr("__author__") = "Mikhail Bessmeltsev (original), adapted for Python";
}
