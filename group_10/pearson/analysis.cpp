/*
Author: David Holmqvist <daae19@student.bth.se>
*/

#include "analysis.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <list>
#include <vector>
#include <pthread.h>

namespace Analysis
{

    // Shared pointers let every POSIX thread access the same input and output.
    // They remain valid because the main thread joins all workers before the
    // local datasets and results vectors leave the parallel
    const std::vector<Vector> *shared_datasets;
    std::vector<double> *shared_results;

    // Workers use this value to divide all correlation pairs into equal ranges.
    std::size_t shared_thread_count;

    /*
     * Worker function run by each POSIX thread.
     *
     * arg: points to this worker's numeric thread ID.
     * work: calculates only the range of dataset pairs assigned to that ID.
     * return: nullptr because the answers are written directly into results.
     *
     * POSIX thread functions must receive and return void pointers. Each worker
     * receives a pointer to its own stable entry in the thread_ids vector.
     */
    void *correlation_worker(void *arg)
    {
        const std::size_t thread_id = *(std::size_t *)arg;
        const std::size_t count = shared_datasets->size();

        // For n datasets there are n * (n - 1) / 2 unique pairs because a
        // dataset is not compared with itself and (A, B) is the same as (B, A).
        const std::size_t pair_count =
            count * (count - 1) / 2;

        // Give this thread an equal range of pair indices.
           // Divide the flattened range [0, pair_count) into contiguous blocks.
        // Integer division also distributes any remainder across the workers.
        const std::size_t begin =
            pair_count * thread_id / shared_thread_count;

        const std::size_t end =
            pair_count * (thread_id + 1) /
            shared_thread_count;

        // This thread may have no work when there are more threads than pairs.
        if (begin == end)
        {
            return nullptr;
        }

        // Convert the first flat pair index into sample1/sample2.
         // The nested sequential loops form a triangular list of pairs:
        // (0,1), (0,2), ..., (1,2), (1,3), ... . Walk over the row lengths
        // until "offset" identifies the pair at this worker's begin index.
        std::size_t offset = begin;
        std::size_t sample1 = 0;

        while (offset >= count - sample1 - 1)
        {
            offset -= count - sample1 - 1;
            sample1++;
        }

        std::size_t sample2 = sample1 + 1 + offset;

        // Process this thread's consecutive range of pairs.
                // Process only this worker's range. Every worker writes to different
        // result indices, so result writes do not require a mutex.
        for (std::size_t pair = begin; pair < end; pair++)
        {
             // pearson receives copies, so all temporary calculations are local
            // to this worker while the shared dataset vector is only read.
            (*shared_results)[pair] =
                Analysis::pearson(
                    (*shared_datasets)[sample1],
                    (*shared_datasets)[sample2]);

            sample2++;

            // Move to the beginning of the next triangular row.
                       // Reaching count finishes one triangular row. Continue at the
            // first valid second sample in the following row.
            if (sample2 == count)
            {
                sample1++;
                sample2 = sample1 + 1;
            }
        }

        return nullptr;
    }

    std::vector<double> correlation_coefficients_parallel(std::vector<Vector> datasets, unsigned int num_threads)
    {

        if (num_threads == 0)
        {
            std::cerr << "Error: Number of threads must be greater than 0." << std::endl;
            std::exit(1);
        }
        const std::size_t dataset_count = datasets.size();
        if (dataset_count < 2)
        {
            std::cerr << "Error: At least two datasets are required to compute correlation coefficients." << std::endl;
            std::exit(1);
        }
        // Pre-allocate all storage before creating threads. This keeps the
        // vector size fixed while workers write their assigned result slots.
        const std::size_t pair_count = dataset_count * (dataset_count - 1) / 2;

        // pthread_t values are needed later so each created thread can be joined.
        std::vector<pthread_t> threads(num_threads);

        // Giving results its final size lets workers write by index without
        // calling push_back, resizing the vector, or changing result order.
        std::vector<double> results(pair_count);
        // Give every worker a separate ID whose address remains valid while it runs.
        std::vector<std::size_t> thread_ids(num_threads);

        // Publish the local vectors to the worker function. The main thread
        // does not modify them until every worker has finished.
        shared_datasets = &datasets;
        shared_results = &results;
        shared_thread_count = num_threads;

        // Count successful creations so pthread_join is called only for valid
        // pthread_t entries if pthread_create fails partway through the loop.
        unsigned int created_threads = 0;

        for (unsigned int thread = 0; thread < num_threads; thread++)
        {
            // Store each ID separately; passing the loop variable itself would
            // let threads observe it after the loop had changed its value.
            thread_ids[thread] = thread;
                   // Start one worker and pass the address of its ID as the argument.
            if (pthread_create(&threads[thread], nullptr, correlation_worker, &thread_ids[thread]) != 0)
            {
                std::cerr << "Error creating thread " << thread << std::endl;
                break;
            }
            created_threads++;
        }

            // Joining waits for every successfully created worker. It guarantees
        // all result elements are ready before the vector is returned.
        for (unsigned int thread = 0; thread < created_threads; thread++)
        {
            
            if (pthread_join(threads[thread], nullptr) != 0)
            {
                std::cerr << "Error joining thread " << thread << std::endl;
            }
        }

           // The workers have finished, so these pointers are no longer needed.
        // Clearing them avoids leaving pointers to local variables behind.
        shared_datasets = nullptr;
        shared_results = nullptr;
        shared_thread_count = 0;

        return results;
    }

  std::vector<double> correlation_coefficients(std::vector<Vector> datasets)
    {
        // Normalize every dataset once before processing any pairs.
        for (auto &dataset : datasets)
        {
            dataset.normalize();
        }

        std::vector<double> result{};
        // Process every unique pair in the same order as the baseline.
        for (auto sample1{0}; sample1 < datasets.size() - 1; sample1++)
        {
            for (auto sample2{sample1 + 1}; sample2 < datasets.size(); sample2++)
            {
                // The Pearson correlation of two normalized vectors is their dot product.
                auto r{datasets[sample1].dot(datasets[sample2])};
                
                // Keep the result within the valid correlation range.
                // Correct possible floating-point values just outside [-1, 1].
                auto corr{std::max(std::min(r, 1.0), -1.0)};

                result.push_back(corr);
            }
        }

        return result;
    }

    double pearson(Vector vec1, Vector vec2)
    {
        auto x_mean{vec1.mean()};
        auto y_mean{vec2.mean()};

        auto x_mm{vec1 - x_mean};
        auto y_mm{vec2 - y_mean};

        auto x_mag{x_mm.magnitude()};
        auto y_mag{y_mm.magnitude()};

        auto x_mm_over_x_mag{x_mm / x_mag};
        auto y_mm_over_y_mag{y_mm / y_mag};

        auto r{x_mm_over_x_mag.dot(y_mm_over_y_mag)};

        return std::max(std::min(r, 1.0), -1.0);
    }
};
