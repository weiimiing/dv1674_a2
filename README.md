# DV1674 Assignment 2

This repository is split into two main directories:

- `group_10/` contains the submission: the Blur and Pearson source code,
  Makefiles, test data, verification scripts, and `report.pdf`.
- `assignment_work/` contains the development material: baselines,
  optimization snapshots, profiling scripts and results, report sources, and
  generated figures.

To validate the submission from the repository root:

```bash
cd group_10
make clean && make
(cd blur && ./verify.sh)
(cd pearson && ./verify.sh)
make clean
```

The corresponding assignment description is available in Canvas.
