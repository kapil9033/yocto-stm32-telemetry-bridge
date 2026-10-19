#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -x "$repo_dir/.venv/bin/python" ]; then
    test_python="$repo_dir/.venv/bin/python"
else
    test_python=python3
fi

"$test_python" -m pytest -m "unit or integration or system"

cmake -S "$repo_dir/gatewayd" -B "$repo_dir/build/gatewayd-tests" -DBUILD_TESTING=ON
cmake --build "$repo_dir/build/gatewayd-tests"
ctest --test-dir "$repo_dir/build/gatewayd-tests" --output-on-failure

cmake -S "$repo_dir/stm32-firmware/tests" -B "$repo_dir/build/firmware-native-tests"
cmake --build "$repo_dir/build/firmware-native-tests"
ctest --test-dir "$repo_dir/build/firmware-native-tests" --output-on-failure
