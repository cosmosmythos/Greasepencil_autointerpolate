#include "stdafx.h"
#include "Smooth.h"

void smooth(std::vector<MyPolyline>& curves, int smoothSteps, double smoothWeight)
{
	// Clamp user inputs to safe ranges
	if (smoothSteps < 0) smoothSteps = 0;
	if (smoothSteps > 20) smoothSteps = 20;
	if (smoothWeight < 0.0) smoothWeight = 0.0;
	if (smoothWeight > 1.0) smoothWeight = 1.0;
	if (smoothSteps == 0 || smoothWeight == 0.0)
		return;

	const int numIter = smoothSteps;
	const double lambda = smoothWeight;
	for (int i = 0; i < numIter; ++i)
	{
		for (int j = 0; j < curves.size(); ++j)
		{
			MyPolyline newPoly = curves[j];
			for (int k = 1; k + 1 < curves[j].size(); ++k)
			{
				Eigen::Vector2d prev = curves[j][k - 1] - curves[j][k];
				Eigen::Vector2d next = curves[j][k + 1] - curves[j][k];
				double wPrev = 1 / prev.norm(), wNext = 1 / next.norm();
				double cosAngle = prev.normalized().dot(next.normalized());
				Eigen::Vector2d L = (wPrev*prev + wNext*next) / (wPrev + wNext);
				newPoly[k] += lambda*L;
			}
			curves[j] = newPoly;
		}
	}
}