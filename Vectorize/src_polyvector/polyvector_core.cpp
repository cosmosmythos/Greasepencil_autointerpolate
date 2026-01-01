#include "polyvector_core.h"
#include "stdafx.h"

// Include all necessary PolyVector headers
#include "graph_typedefs.h"
#include "typedefs.h"
#include "AlmostReebGraph.h"
#include "ChainDecomposition.h"
#include "ContractDeg2.h"
#include "ContractLoops.h"
#include "ContractLoops2.h"
#include "FindRoots.h"
#include "Optimizer.h"
#include "Params.h"
#include "RemoveShortBranches.h"
#include "Simplify.h"
#include "Smooth.h"
#include "SplitEmUp.h"
#include "TopoGraphEmbedding.h"
#include "chopFakeEnds.h"
#include "findSingularities.h"
#include "traceAuto.h"
#include "polynomial_energy.h"

#include "opencv2/core/eigen.hpp"
#include "opencv2/highgui/highgui.hpp"
#include "opencv2/imgproc/imgproc.hpp"

#include <array>
#include <iostream>
#include <fstream>

namespace polyvector {

// Helper functions from main.cpp
static void calculateGradient(const cv::Mat& bwImg, int m, int n,
                               Eigen::MatrixXcd& g, 
                               Eigen::MatrixXcd& tau,
                               Eigen::MatrixXcd& tauTimesGmag,
                               Eigen::MatrixXd& gMag) {
    using namespace cv;
    std::cout << "  DEBUG: calculateGradient entry - input: " << bwImg.rows << "x" 
              << bwImg.cols << " type=" << bwImg.type() << std::endl;
    
    Mat grad_x, grad_y;
    const double scale = 1.0;
    const double delta = 0;

    std::cout << "  DEBUG: Computing Sobel gradients..." << std::endl;
    Sobel(bwImg, grad_x, CV_32F, 1, 0, 3, scale, delta, BORDER_DEFAULT);
    Sobel(bwImg, grad_y, CV_32F, 0, 1, 3, scale, delta, BORDER_DEFAULT);
    std::cout << "  DEBUG: Sobel completed - grad_x: " << grad_x.rows << "x" << grad_x.cols 
              << " type=" << grad_x.type() << std::endl;

    Mat planes[] = {grad_x, grad_y};
    Mat cvG;
    std::cout << "  DEBUG: Merging gradient planes..." << std::endl;
    merge(planes, 2, cvG);
    std::cout << "  DEBUG: Merged cvG: " << cvG.rows << "x" << cvG.cols 
              << " channels=" << cvG.channels() << " type=" << cvG.type() << std::endl;
    
    // OpenCV 4.x compatibility: Ensure g is not locked before conversion
    // cv2eigen may try to reallocate, which fails on locked Mats
    std::cout << "  DEBUG: About to call cv2eigen..." << std::endl;
    cv2eigen(cvG, g);
    std::cout << "  DEBUG: cv2eigen completed successfully!" << std::endl;

    tauTimesGmag = g * std::complex<double>(0.0, 1.0);
    gMag = tauTimesGmag.cwiseAbs();

    double maxGradMag = gMag.maxCoeff();
    for (int i = 0; i < m; ++i) {
        for (int j = 0; j < n; ++j) {
            if (fabs(gMag(i, j) / maxGradMag) < 0.1) {
                gMag(i, j) = 0;
                tauTimesGmag(i, j) = 0;
            }
        }
    }

    Eigen::MatrixXd gMagNoZeros = gMag;
    for (int i = 0; i < m; ++i) {
        for (int j = 0; j < n; ++j) {
            if (fabs(gMag(i, j)) < 1e-10)
                gMagNoZeros(i, j) = 1;
        }
    }

    tau = tauTimesGmag.array() / gMagNoZeros.array();
}

static void calculateWeight(const Eigen::MatrixXcd& tauTimesGmag, int m, int n,
                            Eigen::MatrixXd& weight) {
    using namespace cv;
    std::cout << "  DEBUG: calculateWeight entry - tauTimesGmag size: " << tauTimesGmag.rows() << "x" 
              << tauTimesGmag.cols() << std::endl;

    Eigen::MatrixXcd eigTauTimesGmag2 = tauTimesGmag.array().pow(2);
    // Numerical stability (paper-aligned): avoid division by zero / near-zero.
    // Low-gradient regions are intentionally set to zero in calculateGradient; here we clamp
    // the denominator so weights become large instead of NaN/Inf.
    const double EPSILON = 1e-12;
    for (int i = 0; i < eigTauTimesGmag2.rows(); ++i) {
        for (int j = 0; j < eigTauTimesGmag2.cols(); ++j) {
            if (std::abs(eigTauTimesGmag2(i, j)) < EPSILON) {
                eigTauTimesGmag2(i, j) = std::complex<double>(EPSILON, 0.0);
            }
        }
    }

    Mat eigTauTimesGmag2Re, eigTauTimesGmag2Im;
    Eigen::MatrixXd eigTauTimesGmag2Real = eigTauTimesGmag2.real(),
                    eigTauTimesGmag2Imag = eigTauTimesGmag2.imag();
    
    // OpenCV 4.x compatibility: Release Mats before eigen2cv to avoid locked type errors
    std::cout << "  DEBUG: About to call eigen2cv for real/imag parts..." << std::endl;
    if (!eigTauTimesGmag2Re.empty()) {
        std::cout << "  DEBUG: Releasing eigTauTimesGmag2Re..." << std::endl;
        eigTauTimesGmag2Re.release();
    }
    if (!eigTauTimesGmag2Im.empty()) {
        std::cout << "  DEBUG: Releasing eigTauTimesGmag2Im..." << std::endl;
        eigTauTimesGmag2Im.release();
    }
    std::cout << "  DEBUG: Calling eigen2cv for real part..." << std::endl;
    eigen2cv(eigTauTimesGmag2Real, eigTauTimesGmag2Re);
    std::cout << "  DEBUG: Calling eigen2cv for imag part..." << std::endl;
    eigen2cv(eigTauTimesGmag2Imag, eigTauTimesGmag2Im);
    std::cout << "  DEBUG: Both eigen2cv calls completed!" << std::endl;

    Mat eigTauTimesGmag2ReLaplacian, eigTauTimesGmag2ImLaplacian;
    std::cout << "  DEBUG: Computing Laplacians..." << std::endl;
    // OpenCV 4.x: Ensure destination depth >= source depth.
    // eigTauTimesGmag2Re/Im are created from Eigen doubles, so treat as 64F.
    Laplacian(eigTauTimesGmag2Re, eigTauTimesGmag2ReLaplacian, CV_64F, 1, 1, 0);
    Laplacian(eigTauTimesGmag2Im, eigTauTimesGmag2ImLaplacian, CV_64F, 1, 1, 0);
    std::cout << "  DEBUG: Laplacian completed - about to call cv2eigen..." << std::endl;

    Eigen::MatrixXd lapRe, lapIm;
    // OpenCV 4.x compatibility: cv2eigen on output from Laplacian should be safe
    // but we ensure clean state anyway
    std::cout << "  DEBUG: Calling cv2eigen for Laplacian real..." << std::endl;
    cv2eigen(eigTauTimesGmag2ReLaplacian, lapRe);
    std::cout << "  DEBUG: Calling cv2eigen for Laplacian imag..." << std::endl;
    cv2eigen(eigTauTimesGmag2ImLaplacian, lapIm);
    std::cout << "  DEBUG: cv2eigen Laplacian calls completed!" << std::endl;

    Eigen::MatrixXcd laplacian(m, n);
    for (int i = 0; i < m; ++i) {
        for (int j = 0; j < n; ++j) {
            laplacian(i, j) = std::complex<double>(lapRe(i, j), lapIm(i, j));
        }
    }

    weight = (laplacian.array() / eigTauTimesGmag2.array()).cwiseAbs();
    weight = weight.cwiseMin(1e10);
}

std::vector<std::vector<std::pair<double, double>>> 
vectorize_mat(const cv::Mat& input_image, double threshold) {
    using namespace cv;
    
    std::cout << "\n=== POLYVECTORIZE DEBUG START ===" << std::endl;
    std::cout << "Input image: " << input_image.rows << "x" << input_image.cols 
              << " channels=" << input_image.channels() << " type=" << input_image.type() << std::endl;
    
    std::vector<std::vector<std::pair<double, double>>> result;
    
    try {
        std::cout << "DEBUG: Starting image preprocessing..." << std::endl;
        
        // Convert to grayscale if needed
        cv::Mat bwImg;
        if (input_image.channels() == 3) {
            std::cout << "DEBUG: Converting BGR to GRAY..." << std::endl;
            cvtColor(input_image, bwImg, COLOR_BGR2GRAY);
        } else if (input_image.channels() == 4) {
            std::cout << "DEBUG: Converting BGRA to GRAY..." << std::endl;
            cvtColor(input_image, bwImg, COLOR_BGRA2GRAY);
        } else if (input_image.channels() == 1) {
            std::cout << "DEBUG: Cloning single-channel image..." << std::endl;
            bwImg = input_image.clone();
        } else {
            throw std::runtime_error("Unsupported image format: " + std::to_string(input_image.channels()) + " channels");
        }
        
        // Ensure it's 8-bit grayscale
        if (bwImg.type() != CV_8UC1) {
            std::cout << "DEBUG: Converting to CV_8UC1..." << std::endl;
            bwImg.convertTo(bwImg, CV_8UC1);
        }
        
        std::cout << "DEBUG: Preprocessed image: " << bwImg.rows << "x" << bwImg.cols 
                  << " channels=" << bwImg.channels() << " type=" << bwImg.type() << std::endl;
        
        int m = bwImg.rows;
        int n = bwImg.cols;
        
        if (m == 0 || n == 0) {
            std::cerr << "Empty image" << std::endl;
            return result;
        }

        std::cout << "Processing image: " << m << "x" << n << std::endl;

        // Create mask based on threshold
        cv::Mat origMask = bwImg < threshold;
        origMask = origMask.clone(); // Ensure we own the memory
        
        // Morphological operations
        Mat element = getStructuringElement(MORPH_ELLIPSE, Size(3, 3));
        Mat tempMask;
        morphologyEx(origMask, tempMask, MORPH_CLOSE, element);
        morphologyEx(tempMask, origMask, MORPH_OPEN, element);

        // Calculate gradient and weight
        Eigen::MatrixXcd g, tau, tauTimesGmag;
        Eigen::MatrixXd gMag, weight;
        
        std::cout << "DEBUG: Calling calculateGradient..." << std::endl;
        calculateGradient(bwImg, m, n, g, tau, tauTimesGmag, gMag);
        std::cout << "DEBUG: calculateGradient completed. Result size: " 
                  << g.rows() << "x" << g.cols() << std::endl;
        
        std::cout << "DEBUG: Calling calculateWeight..." << std::endl;
        calculateWeight(tauTimesGmag, m, n, weight);
        std::cout << "DEBUG: calculateWeight completed. Result size: " 
                  << weight.rows() << "x" << weight.cols() << std::endl;

        // Find singularities and optimize
        std::cout << "Optimizing frame field..." << std::endl;
        Eigen::MatrixXi indices = Eigen::MatrixXi::Constant(m, n, -1);
        int curIndex = 0;
        for (int i = 0; i < m; ++i) {
            for (int j = 0; j < n; ++j) {
                if (origMask.at<uchar>(i, j) != 0)
                    indices(i, j) = curIndex++;
            }
        }

        double beta = FRAME_FIELD_REGULARIZER_WEIGHT;
        Eigen::VectorXcd X = optimize(bwImg, weight, tau, beta, origMask, indices);

        // Safety: if optimization diverged (NaN/Inf), do NOT proceed to roots/tracing.
        // This prevents crashes in root finding/tracing when the frame field is invalid.
        if (X.size() == 0) {
            throw std::runtime_error("Optimization failed (empty result)");
        }
        if (!X.allFinite()) {
            throw std::runtime_error("Optimization diverged (NaN/Inf in field)");
        }

        // Find roots
        std::cout << "Finding roots..." << std::endl;
        std::array<Eigen::MatrixXcd, 2> roots = findRoots(X, origMask);

        // Trace polylines
        std::cout << "Tracing polylines..." << std::endl;
        std::map<std::array<int, 2>, std::vector<PixelInfo>> pixelInfo;
        std::vector<std::array<bool, 2>> endedWithASingularity;
        
        cv::Mat extMask = origMask.clone();
        std::vector<MyPolyline> polys = traceAll(bwImg, origMask, extMask, roots, X, indices, 
                                                  pixelInfo, endedWithASingularity);

        if (polys.empty()) {
            std::cout << "No polylines traced" << std::endl;
            return result;
        }

        // Find singularities
        std::set<std::array<int, 2>> singularities = findSingularities(roots, X, indices, origMask);
        std::cout << "Found " << singularities.size() << " singularities" << std::endl;

        // Build Almost Reeb Graph
        std::cout << "Building graph topology..." << std::endl;
        G graph = computeAlmostReebGraph(origMask, roots, polys, pixelInfo, singularities, indices, X, endedWithASingularity);

        // Graph processing pipeline (matches main.cpp exactly)
        std::cout << "Processing graph..." << std::endl;
        
        // Phase 1: Contract singularities and connect
        contractSingularityBranches(graph);
        simpleThresholds(graph);
        connectStuffAroundSingularities(graph, origMask, polys, singularities, roots, endedWithASingularity);
        
        // Phase 2: Set edge weights and contract loops
        for (auto e : boost::make_iterator_range(boost::edges(graph))) {
            graph[e].weight = 1;
        }
        contractLoops(graph, origMask, polys);
        
        // Phase 3: Remove branches and split
        std::map<edge_descriptor, size_t> ignore;
        removeBranchesFilter1(graph, false, ignore);
        splitEmUpCorrectly(graph);
        
        // Phase 4: Contract special degree-2 vertices
        bool chopped = true;
        while (chopped) {
            chopped = false;
            for (size_t v = 0; v < boost::num_vertices(graph); ++v) {
                if ((boost::degree(v, graph) == 2) && 
                    (graph[v].nextToSingularity || graph[v].clusterCurveHitSingularity)) {
                    std::vector<size_t> verts;
                    auto [eit, eend] = boost::out_edges(v, graph);
                    for (; eit != eend; ++eit) {
                        verts.push_back(eit->m_target);
                    }
                    boost::clear_vertex(v, graph);
                    auto e = boost::add_edge(verts[0], verts[1], graph);
                    graph[e.first].edgeCurve = -1;
                }
                if (chopped) break;
            }
        }
        
        // Phase 5: Remove edges between high-valence vertices
        chopped = true;
        while (chopped) {
            chopped = false;
            for (auto [eit, eend] = boost::edges(graph); eit != eend; ++eit) {
                if (boost::degree(eit->m_source, graph) > 2 && 
                    boost::degree(eit->m_target, graph) > 2) {
                    boost::remove_edge(*eit, graph);
                    chopped = true;
                    break;
                }
            }
        }

        // Optimize embedding
        std::cout << "Optimizing embedding..." << std::endl;
        std::vector<MyPolyline> newPolys;
        std::vector<std::vector<double>> radii;
        std::vector<std::array<bool, 2>> protectedEnds;
        std::vector<std::pair<PointOnCurve, PointOnCurve>> yJunctions;
        std::vector<std::array<bool, 2>> isItASpecialDeg2Vertex;
        std::tie(newPolys, radii, protectedEnds, isItASpecialDeg2Vertex, yJunctions) = 
            topoGraphEmbedding(graph, polys, bwImg);
        
        // Chop fake ends
        G wG;
        std::tie(newPolys, wG) = chopFakeEnds(newPolys, radii, protectedEnds, isItASpecialDeg2Vertex, yJunctions);

        // Simplify and smooth (simplified - no component splitting)
        std::cout << "Simplifying and smoothing..." << std::endl;
        std::vector<MyPolyline> newVectorization;
        
        for (size_t i = 0; i < newPolys.size(); ++i) {
            MyPolyline simplified = simplify(newPolys[i], 1e-2);
            if (!simplified.empty()) {
                newVectorization.push_back(simplified);
            }
        }
        
        smooth(newVectorization);

        // Convert to output format
        for (const auto& poly : newVectorization) {
            if (!poly.empty()) {
                std::vector<std::pair<double, double>> points;
                for (const auto& p : poly) {
                    points.push_back({p.x(), p.y()});
                }
                result.push_back(points);
            }
        }

        std::cout << "Vectorization complete: " << result.size() << " strokes" << std::endl;

    } catch (const std::exception& e) {
        // Propagate as Python exception (pybind11 converts std::runtime_error)
        std::cerr << "Error during vectorization: " << e.what() << std::endl;
        throw;
    }

    return result;
}

std::vector<std::vector<std::pair<double, double>>> 
vectorize_image(const std::string& image_path, double threshold) {
    cv::Mat image = cv::imread(image_path, cv::IMREAD_GRAYSCALE);
    
    if (image.empty()) {
        std::cerr << "Failed to load image: " << image_path << std::endl;
        return {};
    }
    
    return vectorize_mat(image, threshold);
}

} // namespace polyvector
