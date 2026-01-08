#ifndef _TYPEDEFS_H_
#define _TYPEDEFS_H_

#define QT_NO_DEBUG_OUTPUT 1

// --- Logging control for Blender addon builds ---
// Default: keep logs concise to avoid overwhelming Blender console.
// Set to 1 at compile time to enable verbose tracing:
//   -DPOLYVECTOR_VERBOSE_LOGS=1
#ifndef POLYVECTOR_VERBOSE_LOGS
#define POLYVECTOR_VERBOSE_LOGS 0
#endif

// Runtime-controlled logging (used by Blender add-on bindings)
//
// We keep all console output disabled by default and only enable it when
// the Python binding passes verbose=True ("Developer" toggle in the UI).
extern bool PV_RUNTIME_VERBOSE;

#define PV_LOG(msg) do { if (PV_RUNTIME_VERBOSE) { std::cout << msg << std::endl; } } while(0)
#define PV_LOG_NL(msg) do { if (PV_RUNTIME_VERBOSE) { std::cout << msg; } } while(0)

// Compile-time verbose logs (legacy; keep for compatibility)
#define PV_VLOG(msg) do { if (POLYVECTOR_VERBOSE_LOGS) { std::cout << msg << std::endl; } } while(0)
#define PV_VLOG_NL(msg) do { if (POLYVECTOR_VERBOSE_LOGS) { std::cout << msg; } } while(0)

#include "Eigen/Dense"
#include "opencv2/core/core.hpp"
#include <vector>
#include <array>

typedef std::vector<Eigen::Vector2d> MyPolyline;
typedef Eigen::Matrix<bool, Eigen::Dynamic, Eigen::Dynamic> BoolMatrix;
struct PixelInfo
{
	int curve;
	Eigen::Vector2d p, tangent;
	double segmentIdx;
};

struct CenterFit
{
	Eigen::Vector2d center, axis;
	double res;
};

struct PointOnCurve
{
	int curve;
	double segmentIdx;
	Eigen::Vector2d p;
	Eigen::Vector2d root;
};

struct Box
{
	double xMin, xMax, yMin, yMax;
	Box() :xMin(std::numeric_limits<double>::max()), xMax(std::numeric_limits<double>::min()), yMin(std::numeric_limits<double>::max()), yMax(std::numeric_limits<double>::min())
	{}

	bool inside(const Eigen::Vector2d& p) const
	{
		return (p.x() > xMin) && (p.x() < xMax) && (p.y() < yMax) && (p.y() > yMin);
	}
	bool completelyOutside(const Eigen::Vector2d& p1, const Eigen::Vector2d& p2)
	{
		if ((p1.x() < xMin) && (p2.x() < xMin))
			return true;
		if ((p1.x() > xMax) && (p2.x() > xMax))
			return true;
		if ((p1.y() < yMin) && (p2.y() < yMin))
			return true;
		if ((p1.y() > yMax) && (p2.y() > yMax))
			return true;
		return false;
	}
};

Box findBoundingBox(const MyPolyline& poly);

Eigen::Vector2d _toEig(std::complex<double> c);
void bitwiseOr(BoolMatrix& lhs, const BoolMatrix& rhs);
bool doesNeighborExist(int i, int j, int m, int n, bool vertical, bool left);
bool useNeighbor(int i, int j, int m, int n, bool vertical, bool left, const cv::Mat & mask, std::pair<int, int>& outNeighbor);
Eigen::Vector2d tangent(const MyPolyline& poly, int i);

template <typename T>
T avg(const std::vector<T>& vec, T zero)
{
	T sum = zero;
	for (int i = 0; i < vec.size(); ++i)
		sum += vec[i];
	return sum / vec.size();
}

bool rootMatching(const std::array<Eigen::MatrixXcd, 2>& roots, const std::array<int, 2>& p0, const std::array<int, 2>& p1);
bool rootMatching(const std::array<std::complex<double>, 2>& r0, const std::array<std::complex<double>, 2>& r1);

bool inBounds(const Eigen::Vector2d& p, const cv::Mat& mask);
bool inBounds(const std::array<int,2>& p, const cv::Mat& mask);
bool inBounds(int i, int j, const cv::Mat& mask);
#endif
