#!/usr/bin/env bash

set -u

echo "NOTE: this script relies on the binaries blur and blur_par to exist"

status=0
if tput setaf 1 &> /dev/null; then
    red=$(tput setaf 1)
    green=$(tput setaf 2)
    reset=$(tput sgr0)
else
    red=""
    green=""
    reset=""
fi

mkdir -p data_o

for image in im1 im2 im3 im4
do
    ./blur 15 "data/$image.ppm" "./data_o/${image}_seq.ppm"
done

for thread in 1 2 4 8 16 32
do
    for image in im1 im2 im3 im4
    do
        ./blur_par 15 "data/$image.ppm" "./data_o/${image}_par.ppm" "$thread"

        if ! cmp -s "./data_o/${image}_seq.ppm" "./data_o/${image}_par.ppm"
        then
            echo "${red}Error: Incongruent output data detected when blurring image $image.ppm with $thread thread(s)${reset}"
            status=1
        else
            echo "${green}Success: Files match for $image.ppm with $thread thread(s).${reset}"
        fi

        rm -f "./data_o/${image}_par.ppm"
    done
done

exit $status
