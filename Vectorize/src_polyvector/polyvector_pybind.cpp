/**
 * Python bindings for PolyVector line art vectorization
 * Using pybind11 for seamless numpy integration
 */

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include "polyvector_core.h"
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
              int smooth_steps,
              double smooth_weight,
              double simplify_epsilon,
              bool verbose) {
    cv::Mat mat = numpy_to_mat(image);
    return vectorize_mat(mat, threshold, blur_pixels, smooth_steps, smooth_weight, simplify_epsilon, verbose);
}

/**
 * Process image file
 */
std::vector<std::vector<std::pair<double, double>>> 
process_file(const std::string& path,
             double threshold,
             int smooth_steps,
             double smooth_weight,
             double simplify_epsilon,
             bool verbose) {
    return vectorize_image(path, threshold, smooth_steps, smooth_weight, simplify_epsilon, verbose);
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
          py::arg("smooth_steps") = 10,
          py::arg("smooth_weight") = 0.5,
          py::arg("simplify_epsilon") = 0.01,
          py::arg("verbose") = false,
          R"doc(
              Vectorize an image file.
              
              Args:
                  image_path: Path to input image (PNG, JPG, etc.)
                  threshold: Background/foreground threshold (0-255, default=90)
                             Lower values = more ink is detected
                  smooth_steps: Number of Laplacian smoothing iterations (0-20, default=10)
                  smooth_weight: Smoothing strength (0.0-1.0, default=0.5)
                  simplify_epsilon: Point reduction tolerance (default=0.01)
                                   Higher values = fewer points, more simplified curves
                                   Lower values = more points, more detail preserved
                  verbose: Enable detailed logging for debugging (default=False)
                             
              Returns:
                  List of polylines, each polyline is a list of (x, y) tuples
                  
              Example:
                  >>> import gp_linevector
                  >>> # Standard usage
                  >>> strokes = gp_linevector.vectorize_image("sketch.png")
                  >>> 
                  >>> # Aggressive simplification for fewer points
                  >>> strokes = gp_linevector.vectorize_image("sketch.png", simplify_epsilon=0.1)
                  >>> 
                  >>> # High detail preservation
                  >>> strokes = gp_linevector.vectorize_image("sketch.png", simplify_epsilon=0.001)
          )doc");

    m.def("vectorize_array", &polyvector::process_numpy,
          py::arg("image"),
          py::arg("threshold") = 90.0,
          py::arg("blur_pixels") = 0,
          py::arg("smooth_steps") = 10,
          py::arg("smooth_weight") = 0.5,
          py::arg("simplify_epsilon") = 0.01,
          py::arg("verbose") = false,
          R"doc(
              Vectorize a numpy array image.
              
              Args:
                  image: Numpy array of shape (H, W) or (H, W, 3) or (H, W, 4)
                         dtype should be uint8
                  threshold: Background/foreground threshold (0-255, default=90)
                  blur_pixels: Gaussian blur preprocessing (0-10, default=0)
                              Helps clean up noisy images before vectorization
                  smooth_steps: Number of Laplacian smoothing iterations (0-20, default=10)
                  smooth_weight: Smoothing strength (0.0-1.0, default=0.5)
                  simplify_epsilon: Point reduction tolerance (default=0.01)
                                   Higher values = fewer points, more simplified curves
                                   Lower values = more points, more detail preserved
                  verbose: Enable detailed logging for debugging (default=False)
                  
              Returns:
                  List of polylines, each polyline is a list of (x, y) tuples
                  
              Example:
                  >>> import gp_linevector
                  >>> import numpy as np
                  >>> from PIL import Image
                  >>> 
                  >>> img = np.array(Image.open("sketch.png"))
                  >>> strokes = gp_linevector.vectorize_array(img)
                  >>> 
                  >>> # With aggressive simplification
                  >>> strokes = gp_linevector.vectorize_array(img, simplify_epsilon=0.1)
          )doc");
    
    // Version info
    m.attr("__version__") = "1.0.0";
    m.attr("__author__") = "Mikhail Bessmeltsev (original), adapted for Python";
}
