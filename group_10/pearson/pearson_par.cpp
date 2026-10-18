/*
Author: David Holmqvist <daae19@student.bth.se>
*/

#include "analysis.hpp"
#include "dataset.hpp"
#include <iostream>
#include <cstdlib>

int main(int argc, char const *argv[])
{
    if (argc != 4)
    {
        std::cerr << "Usage: " << argv[0] << " [infile] [outfile] [num_threads]" << std::endl;
        std::exit(1);
    }
    const int num_threads = std::atoi(argv[3]);
    if (num_threads < 1)
    {
        std::cerr << "num_threads must be positive\n";
        return 1;
    }

    auto datasets{Dataset::read(argv[1])};
    std::vector<double> corrs;
    if (num_threads == 1)
    {
        corrs = Analysis::correlation_coefficients(datasets);
    }
    else
    {
        corrs = Analysis::correlation_coefficients_parallel(datasets, (unsigned int)num_threads);
    }
    Dataset::write(corrs, argv[2]);

    return 0;
}
