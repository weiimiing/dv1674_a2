# Author: David Holmqvist <daae19@student.bth.se>

CXX=g++
CXXFLAGS=-std=c++17 -O2 -g -Wunused -Wall -Wunused
LDFLAGS=-pthread

all: blur blur_par

blur: matrix ppm filters blur.cpp
	$(CXX) $(CXXFLAGS) blur.cpp matrix.o ppm.o filters.o -o blur

blur_par: matrix ppm filters filters_par blur_par.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) blur_par.cpp matrix.o ppm.o filters.o filters_parallel.o -o blur_par

filters: matrix filters.hpp filters.cpp
	$(CXX) $(CXXFLAGS) -c filters.cpp -o filters.o

filters_par: matrix filters_parallel.hpp filters_parallel.cpp
	$(CXX) $(CXXFLAGS) -c filters_parallel.cpp -o filters_parallel.o

matrix: matrix.hpp matrix.cpp
	$(CXX) $(CXXFLAGS) -c matrix.cpp -o matrix.o

ppm: ppm.hpp ppm.cpp
	$(CXX) $(CXXFLAGS) -c ppm.cpp -o ppm.o

clean:
	rm -rf blur blur_par *.ppm *.o *.dSYM 2> /dev/null
