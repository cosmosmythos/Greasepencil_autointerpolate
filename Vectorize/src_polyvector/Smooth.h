#pragma once
#include "typedefs.h"

// Smooth polylines in-place.
// smoothSteps: number of smoothing iterations (0 disables smoothing)
// smoothWeight: step size in [0,1] (0 disables smoothing)
void smooth(std::vector<MyPolyline>& curves, int smoothSteps = 10, double smoothWeight = 0.5);
