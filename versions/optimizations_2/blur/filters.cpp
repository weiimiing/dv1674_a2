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

        const auto w_size = dst.get_x_size();   // loop bound, fetch once not per iteration
        const auto h_size = dst.get_y_size();  
        
        for (auto x{0}; x < w_size; x++)
        {
            for (auto y{0}; y < h_size; y++)
            {
            
                // unsigned char Matrix::r(unsigned x, unsigned y) const
                // {
                //     return R[y * x_size + x];
                // }

                auto r{w[0] * m.r(x, y)}, g{w[0] * m.g(x, y)}, b{w[0] * m.b(x, y)}, n{w[0]};
                for (auto wi{1}; wi <= radius; wi++)
                {
                    auto wc{w[wi]};
                    auto x2{x - wi};
                    if (x2 >= 0)
                    {
                        r += wc * m.r(x2, y);
                        g += wc * m.g(x2, y);
                        b += wc * m.b(x2, y);
                        n += wc;
                    }
                    x2 = x + wi;
                    if (x2 < w_size)
                    {
                        r += wc * m.r(x2, y);
                        g += wc * m.g(x2, y);
                        b += wc * m.b(x2, y);
                        n += wc;
                    }
                }
                scratch.r(x, y) = r / n;
                scratch.g(x, y) = g / n;
                scratch.b(x, y) = b / n;
            }
        }

        for (auto x{0}; x < w_size; x++)
        {
            for (auto y{0}; y < h_size; y++)
            {
            
                auto r{w[0] * scratch.r(x, y)}, g{w[0] * scratch.g(x, y)}, b{w[0] * scratch.b(x, y)}, n{w[0]};

                for (auto wi{1}; wi <= radius; wi++)
                {
                    auto wc{w[wi]};
                    auto y2{y - wi};
                    if (y2 >= 0)
                    {
                        r += wc * scratch.r(x, y2);
                        g += wc * scratch.g(x, y2);
                        b += wc * scratch.b(x, y2);
                        n += wc;
                    }
                    y2 = y + wi;
                    if (y2 < h_size)
                    {
                        r += wc * scratch.r(x, y2);
                        g += wc * scratch.g(x, y2);
                        b += wc * scratch.b(x, y2);
                        n += wc;
                    }
                }
                dst.r(x, y) = r / n;
                dst.g(x, y) = g / n;
                dst.b(x, y) = b / n;
            }
        }

        return dst;
    }

}
