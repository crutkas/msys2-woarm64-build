#!/bin/bash
set -euo pipefail

source `dirname ${BASH_SOURCE[0]}`/../../config.sh

echo "Retaining source-matched CRT bootstrap headers for downstream winpthreads and GCC stages."
