/*
Author: David Holmqvist <daae19@student.bth.se>
*/

#include "analysis.hpp"
#include "dataset.hpp"
#include <iostream>
#include <cstdlib>
#include <utility>

int main(int argc, char const *argv[])
{
    if (argc != 3)
    {
        std::cerr << "Usage: " << argv[0] << " [dataset] [outfile]" << std::endl;
        std::exit(1);
    }

    auto datasets{Dataset::read(argv[1])};
    // Transfer ownership of the dataset storage to correlation_coefficients().
    // The function normalizes its local dataset vectors in place, and datasets
    // is not needed afterward. std::move avoids making a deep copy of every
    // Vector when passing the container by value.
    auto corrs{Analysis::correlation_coefficients(std::move(datasets))};
    Dataset::write(corrs, argv[2]);

    return 0;
}
