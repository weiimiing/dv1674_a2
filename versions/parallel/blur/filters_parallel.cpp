#include "filters_parallel.hpp"
#include "filters.hpp"
#include "matrix.hpp"
#include "ppm.hpp"
#include <pthread.h>
#include <vector>

namespace Filter
{

    namespace
    {
        // Everything a worker needs for pass 1 (horizontal blur).
        struct Pass1Args {
            const Matrix* src;
            Matrix* scratch;
            int radius;
            unsigned w_size;
            unsigned y_start;
            unsigned y_end;
        };

        // Everything a worker needs for pass 2 (vertical blur).
        struct Pass2Args {
            const Matrix* scratch;
            Matrix* dst;
            int radius;
            unsigned w_size;
            unsigned h_size;
            unsigned y_start;
            unsigned y_end;
        };

        // Pass 1 worker: horizontal blur of rows [y_start, y_end).
        void* blur_pass1_worker(void* arg)
        {
            auto* a = static_cast<Pass1Args*>(arg);
            const auto& m  = *a->src;
            auto& scratch  = *a->scratch;
            const int radius = a->radius;
            const unsigned w_size = a->w_size;

            for (auto y = a->y_start; y < a->y_end; ++y)
            {
                for (auto x = 0u; x < w_size; ++x)
                {
                    double w[Gauss::max_radius]{};
                    Gauss::get_weights(radius, w);

                    auto r{ w[0] * m.r(x, y) };
                    auto g{ w[0] * m.g(x, y) };
                    auto b{ w[0] * m.b(x, y) };
                    auto n{ w[0] };

                    for (auto wi{1}; wi <= radius; ++wi)
                    {
                        const auto wc = w[wi];

                        if (static_cast<int>(x) - wi >= 0)
                        {
                            const auto x2 = x - wi;
                            r += wc * m.r(x2, y);
                            g += wc * m.g(x2, y);
                            b += wc * m.b(x2, y);
                            n += wc;
                        }
                        const auto x2r = x + wi;
                        if (x2r < w_size)
                        {
                            r += wc * m.r(x2r, y);
                            g += wc * m.g(x2r, y);
                            b += wc * m.b(x2r, y);
                            n += wc;
                        }
                    }

                    scratch.r(x, y) = r / n;
                    scratch.g(x, y) = g / n;
                    scratch.b(x, y) = b / n;
                }
            }
            return nullptr;
        }

        // Pass 2 worker: vertical blur of rows [y_start, y_end).
        void* blur_pass2_worker(void* arg)
        {
            auto* a = static_cast<Pass2Args*>(arg);
            const auto& scratch = *a->scratch;
            auto& dst = *a->dst;
            const int radius = a->radius;
            const unsigned w_size = a->w_size;
            const unsigned h_size = a->h_size;

            for (auto y = a->y_start; y < a->y_end; ++y)
            {
                for (auto x = 0u; x < w_size; ++x)
                {
                    double w[Gauss::max_radius]{};
                    Gauss::get_weights(radius, w);

                    auto r{ w[0] * scratch.r(x, y) };
                    auto g{ w[0] * scratch.g(x, y) };
                    auto b{ w[0] * scratch.b(x, y) };
                    auto n{ w[0] };

                    for (auto wi{1}; wi <= radius; ++wi)
                    {
                        const auto wc = w[wi];

                        if (static_cast<int>(y) - wi >= 0)
                        {
                            const auto y2 = y - wi;
                            r += wc * scratch.r(x, y2);
                            g += wc * scratch.g(x, y2);
                            b += wc * scratch.b(x, y2);
                            n += wc;
                        }
                        const auto y2b = y + wi;
                        if (y2b < h_size)
                        {
                            r += wc * scratch.r(x, y2b);
                            g += wc * scratch.g(x, y2b);
                            b += wc * scratch.b(x, y2b);
                            n += wc;
                        }
                    }

                    dst.r(x, y) = r / n;
                    dst.g(x, y) = g / n;
                    dst.b(x, y) = b / n;
                }
            }
            return nullptr;
        }
    }

    // Split rows [0, total_rows) into num_chunks contiguous bands.
    static void compute_bands(unsigned total_rows, int num_chunks,
                              std::vector<unsigned>& starts,
                              std::vector<unsigned>& ends)
    {
        starts.resize(num_chunks);
        ends.resize(num_chunks);

        const unsigned chunk = total_rows / static_cast<unsigned>(num_chunks);
        const unsigned rem   = total_rows % static_cast<unsigned>(num_chunks);

        unsigned cursor = 0;
        for (int i = 0; i < num_chunks; ++i)
        {
            starts[i] = cursor;
            unsigned size = chunk + (i < static_cast<int>(rem) ? 1u : 0u);
            cursor += size;
            ends[i] = cursor;
        }
    }

    Matrix blur_parallel(Matrix m, const int radius, const int num_threads)
    {
        // Same allocation pattern as the sequential baseline.
        Matrix scratch{PPM::max_dimension};
        auto dst{m};

        const auto w_size = m.get_x_size();
        const auto h_size = m.get_y_size();

        std::vector<unsigned> y_starts, y_ends;
        compute_bands(h_size, num_threads, y_starts, y_ends);

        std::vector<pthread_t> threads(num_threads);
        std::vector<Pass1Args> a1(num_threads);
        std::vector<Pass2Args> a2(num_threads);

        // ---- Pass 1: horizontal blur, parallel by row bands ----
        for (int i = 0; i < num_threads; ++i)
        {
            a1[i] = { &m, &scratch, radius, w_size, y_starts[i], y_ends[i] };
            pthread_create(&threads[i], nullptr, blur_pass1_worker, &a1[i]);
        }
        for (int i = 0; i < num_threads; ++i)
            pthread_join(threads[i], nullptr);

        // ---- Pass 2: vertical blur, parallel by row bands ----
        for (int i = 0; i < num_threads; ++i)
        {
            a2[i] = { &scratch, &dst, radius, w_size, h_size, y_starts[i], y_ends[i] };
            pthread_create(&threads[i], nullptr, blur_pass2_worker, &a2[i]);
        }
        for (int i = 0; i < num_threads; ++i)
            pthread_join(threads[i], nullptr);

        return dst;
    }

}