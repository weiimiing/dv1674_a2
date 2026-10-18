/*
Author: David Holmqvist <daae19@student.bth.se>
*/

#include "filters.hpp"
#include "matrix.hpp"
#include "ppm.hpp"
#include <cmath>

namespace Filter
{

    namespace Gauss
    {
        void get_weights(int n, double *weights_out)
        {
            for (auto i{0}; i <= n; i++)
            {
                double x{static_cast<double>(i) * max_x / n};
                weights_out[i] = exp(-x * x * pi);
            }
        }
    }

    Matrix blur(Matrix m, const int radius)
    {
        Matrix scratch{PPM::max_dimension};
        Matrix dst{ m.get_x_size(), m.get_y_size(), m.get_color_max() };

        // Weights only depend on radius — compute once, reuse for both passes.
        double w[Gauss::max_radius]{};
        Gauss::get_weights(radius, w);

        const auto w_size = dst.get_x_size();
        const auto h_size = dst.get_y_size();

        // Raw pointers into the pixel buffers. Accessors like m.r(x,y) do
        // a multiply per call; using pointers directly lets hoist the
        // row offset once per row and index by x inside the inner loop.
        const auto* mR = m.get_R();
        const auto* mG = m.get_G();
        const auto* mB = m.get_B();
        auto* sR = scratch.get_R();
        auto* sG = scratch.get_G();
        auto* sB = scratch.get_B();
        auto* dR = dst.get_R();
        auto* dG = dst.get_G();
        auto* dB = dst.get_B();

        //horizontal blur
        
        for (auto y{0}; y < h_size; y++)
        {
            const auto row = y * w_size;   // computed once per row, not per pixel
            for (auto x{0}; x < w_size; x++)
            {
                const auto idx = row + x;   // byte offset of this pixel's channel value

                auto r{ w[0] * mR[idx] };
                auto g{ w[0] * mG[idx] };
                auto b{ w[0] * mB[idx] };
                auto n{ w[0] };

                for (auto wi{1}; wi <= radius; wi++)
                {
                    const auto wc = w[wi];

                    // Left neighbour, if it eists
                    if (x >= wi)
                    {
                        r += wc * mR[row + x - wi];
                        g += wc * mG[row + x - wi];
                        b += wc * mB[row + x - wi];
                        n += wc;
                    }
                    // Right neighbour, if it exists
                    if (x + wi < w_size)
                    {
                        r += wc * mR[row + x + wi];
                        g += wc * mG[row + x + wi];
                        b += wc * mB[row + x + wi];
                        n += wc;
                    }
                }

                sR[idx] = r / n;
                sG[idx] = g / n;
                sB[idx] = b / n;
            }
        }

        //vertical blur 
        for (auto y{0}; y < h_size; y++)
        {
            const auto row = y * w_size;
            for (auto x{0}; x < w_size; x++)
            {
                const auto idx = row + x;

                auto r{ w[0] * sR[idx] };
                auto g{ w[0] * sG[idx] };
                auto b{ w[0] * sB[idx] };
                auto n{ w[0] };

                for (auto wi{1}; wi <= radius; wi++)
                {
                    const auto wc = w[wi];

                    // Top neighbour: same column, wi rows up
                    if (y >= wi)
                    {
                        const auto off = row + x - wi * w_size;
                        r += wc * sR[off];
                        g += wc * sG[off];
                        b += wc * sB[off];
                        n += wc;
                    }
                    // Bottom neighbour: same column, wi rows down.
                    if (y + wi < h_size)
                    {
                        const auto off = row + x + wi * w_size;
                        r += wc * sR[off];
                        g += wc * sG[off];
                        b += wc * sB[off];
                        n += wc;
                    }
                }

                dR[idx] = r / n;
                dG[idx] = g / n;
                dB[idx] = b / n;
            }
        }

        return dst;
    }

}
