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
    
    Mat grad_x, grad_y;
    const double scale = 1.0;
    const double delta = 0;

    Sobel(bwImg, grad_x, CV_32F, 1, 0, 3, scale, delta, BORDER_DEFAULT);
    Sobel(bwImg, grad_y, CV_32F, 0, 1, 3, scale, delta, BORDER_DEFAULT);

    Mat planes[] = {grad_x, grad_y};
    Mat cvG;
    merge(planes, 2, cvG);
    
    // OpenCV 4.x compatibility: Ensure g is not locked before conversion
    // cv2eigen may try to reallocate, which fails on locked Mats
    cv2eigen(cvG, g);

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

static void repairMask(cv::Mat& mask) {
    int m = mask.rows;
    int n = mask.cols;
    std::vector<std::pair<int, int>> newPixels;
    
    for (int i = 0; i < m; ++i) {
        for (int j = 0; j < n; ++j) {
            if (mask.at<uchar>(i, j) == 0) {
                int nn = 0;
                for (int i1 = -1; i1 < 2; ++i1) {
                    for (int j1 = -1; j1 < 2; ++j1) {
                        if ((i1 == j1) || (i1 + i < 0) || (i1 + i >= m) || 
                            (j1 + j < 0) || (j1 + j >= n))
                            continue;

                        if (mask.at<uchar>(i1 + i, j1 + j) != 0)
                            nn++;
                    }
                }
                if (nn >= 5) {
                    newPixels.push_back({i, j});
                }
            }
        }
    }

    for (auto p : newPixels)
        mask.at<uchar>(p.first, p.second) = 255;
}

static std::vector<cv::Mat> computeComponentMasks(const cv::Mat& binMask) {
    CV_Assert(!binMask.empty());
    CV_Assert(binMask.type() == CV_8U);

    // labels: CV_32S, values 0..numLabels-1 where 0 is background.
    cv::Mat labels;
    int numLabels = cv::connectedComponents(binMask, labels, 8, CV_32S);

    std::vector<cv::Mat> masks;
    masks.reserve(std::max(0, numLabels - 1));
    for (int lbl = 1; lbl < numLabels; ++lbl) { // skip label 0 (background)
        cv::Mat comp = (labels == lbl);  // yields CV_8U with 0 or 255
        masks.push_back(comp);
    }
    return masks;
}

static void calculateWeight(const Eigen::MatrixXcd& tauTimesGmag, const Eigen::MatrixXcd& tau,
                            const Eigen::MatrixXd& gMag, int m, int n,
                            Eigen::MatrixXd& weight) {
    using namespace cv;

    Eigen::MatrixXcd eigTauTimesGmag2 = tauTimesGmag.array().pow(2);

    // Convert to cv::Mat for filter2D
    Mat eigTauTimesGmag2Re, eigTauTimesGmag2Im;
    Eigen::MatrixXd eigTauTimesGmag2Real = eigTauTimesGmag2.real(),
                    eigTauTimesGmag2Imag = eigTauTimesGmag2.imag();
    
    eigen2cv(eigTauTimesGmag2Real, eigTauTimesGmag2Re);
    eigen2cv(eigTauTimesGmag2Imag, eigTauTimesGmag2Im);

    // Use filter2D with custom kernel (NOT Laplacian!)
    Mat Lx, Ly;
    Mat kernel;
    kernel = Mat::ones(3, 3, CV_64F);
    kernel.at<double>(1, 1) = 0;  // Center is 0, neighbors are 1
    
    filter2D(eigTauTimesGmag2Re, Lx, -1, kernel);
    filter2D(eigTauTimesGmag2Im, Ly, -1, kernel);

    Eigen::MatrixXd Lx_eig, Ly_eig;
    cv2eigen(Lx, Lx_eig);
    cv2eigen(Ly, Ly_eig);

    Eigen::MatrixXcd mse = Lx_eig + std::complex<double>(0, 1) * Ly_eig;
    Eigen::MatrixXd mseNorm = mse.cwiseAbs();
    
    // Normalize
    for (int i = 0; i < m; ++i)
        for (int j = 0; j < n; ++j)
            if (mseNorm(i, j) < 1e-10)
                mseNorm(i, j) = 1;

    mse = mse.array() / mseNorm.array();

    // Subtract tau^2
    Eigen::MatrixXcd tau2 = tau.array().pow(2);
    mse = mse - tau2;

    // Zero out low gradient regions
    for (int i = 0; i < m; ++i)
        for (int j = 0; j < n; ++j)
            if (fabs(gMag(i, j)) < 1e-10)
                mse(i, j) = 0;

    weight = mse.cwiseAbs();

    // CRITICAL: Invert the weight! (1 - normalized)
    weight = Eigen::MatrixXd::Ones(m, n) - weight / weight.maxCoeff();

    // Final cleanup: zero out low gradient
    for (int i = 0; i < m; ++i)
        for (int j = 0; j < n; ++j)
            if (fabs(gMag(i, j)) < 1e-10)
                weight(i, j) = 0;
}

std::vector<std::vector<std::pair<double, double>>> 
vectorize_mat(const cv::Mat& input_image, double threshold) {
    using namespace cv;
    
    std::vector<std::vector<std::pair<double, double>>> result;
    
    try {
        // Convert to grayscale if needed
        cv::Mat bwImg;
        if (input_image.channels() == 3) {
            cvtColor(input_image, bwImg, COLOR_BGR2GRAY);
        } else if (input_image.channels() == 4) {
            cvtColor(input_image, bwImg, COLOR_BGRA2GRAY);
        } else if (input_image.channels() == 1) {
            bwImg = input_image.clone();
        } else {
            throw std::runtime_error("Unsupported image format: " + std::to_string(input_image.channels()) + " channels");
        }
        
        // Ensure it's 8-bit grayscale
        if (bwImg.type() != CV_8UC1) {
            bwImg.convertTo(bwImg, CV_8UC1);
        }
        
        int m = bwImg.rows;
        int n = bwImg.cols;
        
        if (m == 0 || n == 0) {
            std::cerr << "Empty image" << std::endl;
            return result;
        }

        std::cout << "Processing image: " << m << "x" << n << std::endl;

        // CRITICAL: Invert image before thresholding (matches master line 388!)
        // This is essential for correct mask generation
        bwImg = cv::Scalar(255) - bwImg;

        // Create mask based on threshold (matches master line 402)
        cv::Mat origMask;
        cv::threshold(bwImg, origMask, threshold, 255, cv::THRESH_BINARY);

        // Calculate gradient and weight
        Eigen::MatrixXcd g, tau, tauTimesGmag;
        Eigen::MatrixXd gMag, weight;
        
        calculateGradient(bwImg, m, n, g, tau, tauTimesGmag, gMag);
        calculateWeight(tauTimesGmag, tau, gMag, m, n, weight);

        // Repair mask to fill small gaps (CRITICAL: matches master!)
        // This reduces fragmentation by connecting nearby regions
        for (int i = 0; i < 3; ++i) {
            repairMask(origMask);
        }

        // Split into connected components (KEY: matches master!)
        auto componentMasks = computeComponentMasks(origMask);
        std::cout << "Found " << componentMasks.size() << " connected component(s)." << std::endl;

        double beta = FRAME_FIELD_SMOOTHNESS_WEIGHT;
        std::vector<MyPolyline> allVectorization;

        // Process each component separately (THIS IS THE FIX!)
        for (size_t compIdx = 0; compIdx < componentMasks.size(); ++compIdx) {
            std::cout << "COMPONENT " << compIdx << " / " << componentMasks.size() << std::endl;
            cv::Mat& compMask = componentMasks[compIdx];
            
            // Calculate indices for this component
            Eigen::MatrixXi indices = Eigen::MatrixXi::Constant(m, n, -1);
            int nnz = 0;
            for (int i = 0; i < m; ++i) {
                for (int j = 0; j < n; ++j) {
                    if (compMask.at<uchar>(i, j) != 0)
                        indices(i, j) = nnz++;
                }
            }

            // Optimize for this component
            std::cout << "Optimizing..." << std::flush;
            Eigen::VectorXcd X = optimizeByLinearSolve(bwImg, weight, tau, beta, compMask, indices);
            if (X.size() == 0) {
                X = optimize(bwImg, weight, tau, beta, compMask, indices);
            }
            std::cout << "done. " << std::endl;

            // Safety check
            if (X.size() == 0 || !X.allFinite()) {
                std::cout << "Component " << compIdx << " optimization failed, skipping." << std::endl;
                continue;
            }

            // Find roots for this component
            std::cout << "Finding roots.. " << std::flush;
            auto compRoots = findRoots(X, compMask);

            // Iteratively remove singularities
            auto singularities = findSingularities(compRoots, X, indices, compMask);
            
            // Print initial singularities (matches master line 453)
            std::cout << "Singularities: ";
            for (auto s : singularities) {
                std::cout << s[0] << ", " << s[1] << "; ";
            }
            std::cout << std::endl;
            bool improved;
            do {
                int origSingularityCount = singularities.size();

                bool somethingNew = false;
                for (auto s : singularities) {
                    if (weight(s[0], s[1]) > 1e-5) {
                        somethingNew = true;
                        weight(s[0], s[1]) = 0;
                    }
                }
                if (!somethingNew)
                    break;

                X = optimizeByLinearSolve(bwImg, weight, tau, beta, compMask, indices);
                if (X.size() == 0) {
                    X = optimize(bwImg, weight, tau, beta, compMask, indices);
                }
                compRoots = findRoots(X, compMask);
                singularities = findSingularities(compRoots, X, indices, compMask);

                std::cout << "done (" << origSingularityCount - (int)singularities.size() << " singularities removed)" << std::endl;
                improved = origSingularityCount - singularities.size() > 0;
            } while (improved);

            std::cout << "Done." << std::endl;

            // Trace polylines for this component
            std::map<std::array<int, 2>, std::vector<PixelInfo>> pixelInfo;
            std::vector<std::array<bool, 2>> endedWithASingularity;
            
            auto compPolys = traceAll(bwImg, compMask, compMask, compRoots, X, indices, 
                                      pixelInfo, endedWithASingularity);
            
            std::cout << "Done. " << compPolys.size() << " curves" << std::endl;

            if (compPolys.empty()) {
                std::cout << "No polylines traced for component " << compIdx << std::endl;
                continue;
            }

            // Build Almost Reeb Graph for this component
            G reebGraph = computeAlmostReebGraph(compMask, compRoots, compPolys, pixelInfo, 
                                                  singularities, indices, X, endedWithASingularity);

            // Graph processing pipeline (matches main.cpp exactly)
            contractSingularityBranches(reebGraph);
            simpleThresholds(reebGraph);
            connectStuffAroundSingularities(reebGraph, compMask, compPolys, singularities, compRoots, endedWithASingularity);
            
            for (auto e : boost::make_iterator_range(boost::edges(reebGraph))) {
                reebGraph[e].weight = 1;
            }
            contractLoops(reebGraph, compMask, compPolys);
            
            std::map<edge_descriptor, size_t> ignore;
            removeBranchesFilter1(reebGraph, false, ignore);
            splitEmUpCorrectly(reebGraph);
            
            // Contract special degree-2 vertices
            bool chopped = true;
            while (chopped) {
                chopped = false;
                for (size_t v = 0; v < boost::num_vertices(reebGraph); ++v) {
                    if ((boost::degree(v, reebGraph) == 2) && 
                        (reebGraph[v].nextToSingularity || reebGraph[v].clusterCurveHitSingularity)) {
                        std::vector<size_t> verts;
                        auto [eit, eend] = boost::out_edges(v, reebGraph);
                        for (; eit != eend; ++eit) {
                            verts.push_back(eit->m_target);
                        }
                        boost::clear_vertex(v, reebGraph);
                        auto e = boost::add_edge(verts[0], verts[1], reebGraph);
                        reebGraph[e.first].edgeCurve = -1;
                    }
                    if (chopped) break;
                }
            }
            
            // Remove edges between high-valence vertices
            chopped = true;
            while (chopped) {
                chopped = false;
                for (auto [eit, eend] = boost::edges(reebGraph); eit != eend; ++eit) {
                    if (boost::degree(eit->m_source, reebGraph) > 2 && 
                        boost::degree(eit->m_target, reebGraph) > 2) {
                        boost::remove_edge(*eit, reebGraph);
                        chopped = true;
                        break;
                    }
                }
            }

            // Optimize embedding for this component
            std::vector<MyPolyline> compVectorization;
            std::vector<std::vector<double>> radii;
            std::vector<std::array<bool, 2>> protectedEnds;
            std::vector<std::pair<PointOnCurve, PointOnCurve>> yJunctions;
            std::vector<std::array<bool, 2>> isItASpecialDeg2Vertex;
            std::tie(compVectorization, radii, protectedEnds, isItASpecialDeg2Vertex, yJunctions) = 
                topoGraphEmbedding(reebGraph, compPolys, bwImg);
            
            // Chop fake ends
            G wG;
            std::tie(compVectorization, wG) = chopFakeEnds(compVectorization, radii, protectedEnds, 
                                                           isItASpecialDeg2Vertex, yJunctions);

            // CRITICAL: Set edge weights for cycle detection (matches master line 573-577)
            for (auto [eit, eend] = boost::edges(wG); eit != eend; ++eit) {
                wG[*eit].weight = 1.0;
            }

            // CRITICAL: Find and remove cycles (matches master line 579-590)
            std::cout << "Finding cycles: ";
            std::vector<edge_descriptor> removedEdges;
            if (boost::num_edges(wG) < 350) {
                std::cout << "Using Tarjan's algorithm " << std::endl;
                removedEdges = contractLoops2(wG, compMask, compVectorization);
            } else {
                std::cout << "Using min spanning trees algorithm " << std::endl;
                removedEdges = contractLoops(wG, compMask, compVectorization);
            }

            // CRITICAL: Cut polylines at cycle intersections (matches master line 591-633)
            std::vector<std::vector<std::pair<double, double>>> cutThosePieces(compVectorization.size());
            int totalCuts = 0;
            for (auto e : removedEdges) {
                int curve = wG[e.m_source].clusterPoints[0].curve;
                if (curve == wG[e.m_target].clusterPoints[0].curve) {
                    double s1 = wG[e.m_source].clusterPoints[0].segmentIdx;
                    double s2 = wG[e.m_target].clusterPoints[0].segmentIdx;
                    cutThosePieces[curve].push_back(std::minmax(s1, s2));
                    totalCuts++;
                }
            }
            std::cout << "DEBUG: Total cuts to apply: " << totalCuts << " across " << compVectorization.size() << " curves" << std::endl;

            // Split polylines based on cut points
            std::vector<MyPolyline> compNewVectorization;
            int curvesWithCuts = 0;
            int totalSegmentsCreated = 0;
            for (size_t i = 0; i < compVectorization.size(); ++i) {
                if (compVectorization[i].empty())
                    continue;

                std::vector<std::pair<double, double>> segments;
                std::sort(cutThosePieces[i].begin(), cutThosePieces[i].end(), 
                         [](const std::pair<double, double>& p1, const std::pair<double, double>& p2) {
                             return p1.first < p2.first;
                         });
                segments.push_back({0.0, 0.0});
                for (size_t j = 0; j < cutThosePieces[i].size(); ++j) {
                    segments.back().second = cutThosePieces[i][j].first;
                    segments.push_back({cutThosePieces[i][j].second, 0.0});
                }
                segments.back().second = compVectorization[i].size() - 1;
                
                if (cutThosePieces[i].size() > 0) {
                    curvesWithCuts++;
                }

                // Create new polylines from segments
                for (size_t j = 0; j < segments.size(); ++j) {
                    MyPolyline newPoly;
                    if (fabs(segments[j].second - segments[j].first) > 1e-5) {
                        for (int k = static_cast<int>(segments[j].first); k <= static_cast<int>(segments[j].second); ++k) {
                            if (newPoly.empty() || (newPoly.back() - compVectorization[i][k]).norm() > 1e-6)
                                newPoly.push_back(compVectorization[i][k]);
                        }
                    }
                    if (!newPoly.empty()) {
                        compNewVectorization.push_back(newPoly);
                        totalSegmentsCreated++;
                    }
                }
            }
            std::cout << "DEBUG: Split " << curvesWithCuts << " curves into " << totalSegmentsCreated << " segments (from " << compVectorization.size() << " input curves)" << std::endl;

            // Simplify and smooth (matches master line 635-638)
            for (size_t i = 0; i < compNewVectorization.size(); ++i) {
                compNewVectorization[i] = simplify(compNewVectorization[i], 1e-2);
            }
            
            smooth(compNewVectorization);

            // Accumulate results from this component
            allVectorization.insert(allVectorization.end(), 
                                   compNewVectorization.begin(), 
                                   compNewVectorization.end());
        }

        std::cout << "Simplifying and smoothing..." << std::endl;

        // Convert to output format
        for (const auto& poly : allVectorization) {
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
