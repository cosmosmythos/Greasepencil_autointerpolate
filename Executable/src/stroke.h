/**
 * @file stroke.h
 * @brief Core stroke data structures for FTP-SC algorithm
 * 
 * Based on Yang et al. 2018 "FTP-SC: Fuzzy Topology Preserving Stroke Correspondence"
 * 
 * This file contains the fundamental data structures used throughout the FTP-SC
 * implementation, following the paper's notation as closely as possible.
 */

#pragma once

#include <vector>
#include <optional>
#include <cmath>
#include <limits>

namespace ftpsc {

/**
 * @brief 2D vector for stroke coordinates
 * 
 * Note: While Blender GPv3 uses 3D coordinates, the FTP-SC algorithm operates
 * in 2D. The projection from 3D to 2D happens at the interface layer.
 */
struct Vec2 {
    double x, y;
    
    Vec2() : x(0.0), y(0.0) {}
    Vec2(double x_, double y_) : x(x_), y(y_) {}
    
    // Vector operations
    Vec2 operator+(const Vec2& other) const {
        return Vec2(x + other.x, y + other.y);
    }
    
    Vec2 operator-(const Vec2& other) const {
        return Vec2(x - other.x, y - other.y);
    }
    
    Vec2 operator*(double scalar) const {
        return Vec2(x * scalar, y * scalar);
    }
    
    Vec2 operator/(double scalar) const {
        return Vec2(x / scalar, y / scalar);
    }
    
    // Dot product
    double dot(const Vec2& other) const {
        return x * other.x + y * other.y;
    }
    
    // Length (magnitude)
    double length() const {
        return std::sqrt(x * x + y * y);
    }
    
    // Squared length (avoid sqrt when possible)
    double length_squared() const {
        return x * x + y * y;
    }
    
    // Normalized vector
    Vec2 normalized() const {
        double len = length();
        if (len < 1e-10) {
            return Vec2(0.0, 0.0);
        }
        return Vec2(x / len, y / len);
    }
    
    // Distance to another point
    double distance_to(const Vec2& other) const {
        return (*this - other).length();
    }
};

/**
 * @brief A stroke represented as a polyline
 * 
 * This is the fundamental data structure in FTP-SC. A stroke is a sequence
 * of 2D points representing a drawn curve.
 */
struct Stroke {
    std::vector<Vec2> points;
    
    // Optional: Store original 3D data if needed for reconstruction
    // std::vector<Vec3> points_3d;
    
    // Cached computed properties (mutable to allow lazy evaluation in const methods)
    mutable std::optional<Vec2> cached_centroid;
    mutable std::optional<double> cached_arc_length;
    mutable std::optional<std::vector<double>> cached_arc_params;
    
    /**
     * @brief Get the centroid (barycenter) of the stroke
     * @return The geometric center of all points
     */
    Vec2 get_centroid() const {
        if (!cached_centroid) {
            if (points.empty()) {
                cached_centroid = Vec2(0.0, 0.0);
            } else {
                Vec2 sum(0.0, 0.0);
                for (const auto& p : points) {
                    sum = sum + p;
                }
                cached_centroid = sum / static_cast<double>(points.size());
            }
        }
        return *cached_centroid;
    }
    
    /**
     * @brief Get the total arc length of the stroke
     * @return Sum of distances between consecutive points
     */
    double get_arc_length() const {
        if (!cached_arc_length) {
            double length = 0.0;
            for (size_t i = 1; i < points.size(); ++i) {
                length += points[i].distance_to(points[i-1]);
            }
            cached_arc_length = length;
        }
        return *cached_arc_length;
    }
    
    /**
     * @brief Get arc-length parameterization of vertices
     * @return Vector of parameters in [0,1] for each vertex
     * 
     * This is equation-related from Yang-Feng 2009 Section 3.2.1:
     * Parameters t₁, t₂, ..., tₙ where t₁=0 and tₙ=1
     */
    const std::vector<double>& get_arc_parameters() const {
        if (!cached_arc_params) {
            cached_arc_params = std::vector<double>();
            cached_arc_params->reserve(points.size());
            
            if (points.empty()) {
                return *cached_arc_params;
            }
            
            cached_arc_params->push_back(0.0);
            
            double total_length = get_arc_length();
            if (total_length < 1e-10) {
                // Degenerate stroke - all points at same location
                for (size_t i = 1; i < points.size(); ++i) {
                    cached_arc_params->push_back(0.0);
                }
                return *cached_arc_params;
            }
            
            double accum = 0.0;
            for (size_t i = 1; i < points.size(); ++i) {
                accum += points[i].distance_to(points[i-1]);
                cached_arc_params->push_back(accum / total_length);
            }
        }
        return *cached_arc_params;
    }
    
    /**
     * @brief Get start point of stroke
     */
    Vec2 get_start() const {
        return points.empty() ? Vec2(0.0, 0.0) : points.front();
    }
    
    /**
     * @brief Get end point of stroke
     */
    Vec2 get_end() const {
        return points.empty() ? Vec2(0.0, 0.0) : points.back();
    }
    
    /**
     * @brief Check if stroke is valid (has at least 2 points)
     */
    bool is_valid() const {
        return points.size() >= 2;
    }
    
    /**
     * @brief Invalidate cached values (call when points are modified)
     */
    void invalidate_cache() {
        cached_centroid.reset();
        cached_arc_length.reset();
        cached_arc_params.reset();
    }
    
    /**
     * @brief Get number of points
     */
    size_t size() const {
        return points.size();
    }
};

/**
 * @brief Extract a stroke from raw point data
 * @param coords Flat array of coordinates [x0, y0, x1, y1, ...]
 * @param num_points Number of points in the stroke
 * @return Constructed stroke
 */
inline Stroke create_stroke_from_coords(const double* coords, size_t num_points) {
    Stroke stroke;
    stroke.points.reserve(num_points);
    
    for (size_t i = 0; i < num_points; ++i) {
        stroke.points.emplace_back(coords[i * 2], coords[i * 2 + 1]);
    }
    
    return stroke;
}

/**
 * @brief Extract strokes from raw point data with 3D coordinates
 * @param coords Flat array of coordinates [x0, y0, z0, x1, y1, z1, ...]
 * @param num_points Number of points in the stroke
 * @param project_to_2d Function to project 3D to 2D (e.g., drop Z, or use camera projection)
 * @return Constructed stroke
 */
template<typename ProjectFunc>
inline Stroke create_stroke_from_3d_coords(
    const double* coords,
    size_t num_points,
    ProjectFunc project_to_2d
) {
    Stroke stroke;
    stroke.points.reserve(num_points);
    
    for (size_t i = 0; i < num_points; ++i) {
        double x = coords[i * 3];
        double y = coords[i * 3 + 1];
        double z = coords[i * 3 + 2];
        
        auto [x2d, y2d] = project_to_2d(x, y, z);
        stroke.points.emplace_back(x2d, y2d);
    }
    
    return stroke;
}

} // namespace ftpsc
