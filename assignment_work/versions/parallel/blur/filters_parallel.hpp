#if !defined(FILTERS_PARALLEL_HPP)
#define FILTERS_PARALLEL_HPP

#include "matrix.hpp"

namespace Filter
{
    // Parallel version of blur. Splits both passes into horizontal
    // bands of rows, one per thread. With num_threads = 1, output is
    // byte-identical to Filter::blur.
    Matrix blur_parallel(Matrix m, const int radius, const int num_threads);
}

#endif
