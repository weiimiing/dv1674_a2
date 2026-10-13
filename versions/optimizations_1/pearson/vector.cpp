/*
Author: David Holmqvist <daae19@student.bth.se>
*/

#include "vector.hpp"
#include <iostream>
#include <cmath>
#include <vector>

Vector::Vector()
    : size{0}, data{nullptr}
{
}

Vector::~Vector()
{
    if (data)
    {
        delete[] data;
    }

    size = 0;
}

Vector::Vector(unsigned size)
    : size{size}, data{new double[size]}
{
}

Vector::Vector(unsigned size, double *data)
    : size{size}, data{data}
{
}

Vector::Vector(const Vector &other)
    : Vector{other.size}
{
    for (auto i{0}; i < size; i++)
    {
        data[i] = other.data[i];
    }
}

unsigned Vector::get_size() const
{
    return size;
}

double *Vector::get_data()
{
    return data;
}

double Vector::operator[](unsigned i) const
{
    return data[i];
}

double &Vector::operator[](unsigned i)
{
    return data[i];
}

double Vector::mean() const
{
    double sum{0};

    for (auto i{0}; i < size; i++)
    {
        sum += data[i];
    }

    return sum / static_cast<double>(size);
}

double Vector::magnitude() const
{
    auto dot_prod{dot(*this)};
    return std::sqrt(dot_prod);
}

Vector Vector::operator/(double div)
{
    auto result{*this};

    for (auto i{0}; i < size; i++)
    {
        result[i] /= div;
    }

    return result;
}

Vector Vector::operator-(double sub)
{
    auto result{*this};

    for (auto i{0}; i < size; i++)
    {
        result[i] -= sub;
    }

    return result;
}
/// @brief Centre and normalize this vector in place.
/// @details This function is used before the correlation pair loops so each dataset
// is normalized only once. After normalization, the vector has a mean of
// approximately zero and a magnitude of one. The Pearson correlation of
// two normalized vectors can therefore be calculated with one dot product.
// Modifying the existing data avoids allocating temporary vectors subtraction and division, which is more efficient. 
void Vector::normalize(){

    // Calculate the mean once. It remains constant while centering every
    // element, so it is kept outside the following loop.
    const double average = mean();
    double squared_magnitude = 0.0;

    // Subtract the mean and calculate the squared magnitude in the same
    // loop. This loop fusion avoids making two separate passes over data.
    for (unsigned i = 0; i < size; ++i) {
        data[i] -= average;
        squared_magnitude += data[i] * data[i];
    }
    // Calculate the square root and division only once. Multiplication by
    // the reciprocal below is less expensive than dividing every element.
    const double inverse_magnitude = 1.0 / std::sqrt(squared_magnitude);

     // Scale the centred values so the vector has a magnitude of one.
    for (unsigned i = 0; i < size; ++i) {
        data[i] *= inverse_magnitude;  
    }
}
/// @brief Calculate the dot product of this vector and another vector.
/// @param rhs The vector to calculate the dot product with.
/// @return The dot product of the two vectors.
/// @details Accept rhs as a const reference instead of passing it by value.
/// This avoids creating a deep copy of the Vector for every dot product.
/// The const qualifier guarantees that dot() cannot modify rhs and also
/// allows const Vector objects, such as *this inside magnitude(), to be used.
double Vector::dot(const Vector& rhs) const
{
    double result{0};

    for (auto i{0}; i < size; i++)
    {
        result += data[i] * rhs[i];
    }

    return result;
}