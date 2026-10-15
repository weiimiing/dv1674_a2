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

void Vector:: normalize(){
    // The mean is constant for every element in this vector.
    const double average = mean();

    // Centre the vector so its mean becomes approximately zero.
    for (unsigned i = 0; i < size; ++i) {
        data[i] -= average;
    }
    // Calculate the magnitude after the values have been centred.
     const double magnitude_value = magnitude();
    // Scale the centred vector so its magnitude becomes one.
    for (unsigned i = 0; i < size; ++i) {
        data[i] /= magnitude_value;
    }
}


double Vector::dot(Vector rhs) const
{
    double result{0};

    for (auto i{0}; i < size; i++)
    {
        result += data[i] * rhs[i];
    }

    return result;
}