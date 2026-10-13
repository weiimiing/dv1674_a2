/*
Author: David Holmqvist <daae19@student.bth.se>
*/

#include "analysis.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <list>
#include <vector>

namespace Analysis {

std::vector<double> correlation_coefficients(std::vector<Vector> datasets)
{

    const std::size_t count = datasets.size();

    // Centre and normalize each vector once before processing pairs.
    // This hoists repeated mean and magnitude calculations out of the
    // nested loops. The input is passed by value, so it can be modified.
    for (auto& dataset : datasets) {
        dataset.normalize();
    }

    std::vector<double> result {};

    // There are n * (n - 1) / 2 unique pairs. Reserving this capacity
    // prevents repeated reallocations while results are appended.
    result.reserve(datasets.size() * (datasets.size() - 1) / 2);

    // Calculate each unique pair once, excluding self-correlations and
    // avoiding duplicate pairs such as both (a, b) and (b, a).
    for (std::size_t sample1 = 0;
         sample1 + 1 < count;
         ++sample1) {
        for (std::size_t sample2 = sample1 + 1;
             sample2 < count;
             ++sample2) {
            // Since both vectors are already normalized, their Pearson
            // correlation coefficient is their dot product.
            const double correlation =
                datasets[sample1].dot(datasets[sample2]);

            // Correct small floating-point rounding errors that could
            // otherwise produce a value slightly outside [-1, 1].
            result.push_back(
                std::clamp(correlation, -1.0, 1.0));
        }
    }

    return result;
}

double pearson(Vector vec1, Vector vec2)
{
    auto x_mean { vec1.mean() };
    auto y_mean { vec2.mean() };

    auto x_mm { vec1 - x_mean };
    auto y_mm { vec2 - y_mean };

    auto x_mag { x_mm.magnitude() };
    auto y_mag { y_mm.magnitude() };

    auto x_mm_over_x_mag { x_mm / x_mag };
    auto y_mm_over_y_mag { y_mm / y_mag };

    auto r { x_mm_over_x_mag.dot(y_mm_over_y_mag) };

    return std::max(std::min(r, 1.0), -1.0);
}
};
