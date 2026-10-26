#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
gcov_tool=${GCOV:-gcov}

if [ -x "$repo_dir/.venv/bin/python" ]; then
    test_python="$repo_dir/.venv/bin/python"
else
    test_python=python3
fi

coverage_root="$repo_dir/build/coverage"
mkdir -p "$coverage_root"
python_results="$coverage_root/python-results.xml"
python_log="$coverage_root/python-tests.log"
pytest_status=0
if "$test_python" -m pytest -m "unit or integration or system or hil" \
    --junitxml="$python_results" >"$python_log" 2>&1; then
    cat "$python_log"
else
    pytest_status=$?
    cat "$python_log"
fi

coverage_build="$repo_dir/build/unit-mcdc-coverage"
cmake -S "$repo_dir/tests/unit" -B "$coverage_build" -DENABLE_MCDC_COVERAGE=ON
cmake --build "$coverage_build"
native_status=0
if ctest --test-dir "$coverage_build" --output-on-failure \
    --output-log "$coverage_root/native-tests.log"; then
    :
else
    native_status=$?
fi

if ! command -v "$gcov_tool" >/dev/null 2>&1; then
    printf 'ERROR: %s is required to report native MC/DC coverage.\n' "$gcov_tool" >&2
    exit 1
fi

coverage_report="$coverage_build/gcov-report"
mkdir -p "$coverage_report"
coverage_summary="$coverage_report/summary.txt"
: > "$coverage_summary"
printf '\nNative per-file coverage (line, branch, and masking MC/DC):\n'
find "$coverage_build/CMakeFiles" -type f -name '*.gcno' -print | sort | while IFS= read -r notes_file; do
    notes_name=${notes_file##*/}
    case "$notes_name" in
        *_test.*.gcno) continue ;;
    esac
    gcov_output=$(cd "$coverage_report" && "$gcov_tool" --conditions --branch-probabilities "$notes_file")
    file_summary=$(printf '%s\n' "$gcov_output" | awk -v root="$repo_dir/" '
        /^File / {
            current = index($0, root) > 0 && $0 !~ /_test[.]/
            if (current) print
            next
        }
        /^Creating / { current = 0; next }
        /^(Lines executed:|Branches executed:|Taken at least once:|Condition outcomes covered:)/ {
            if (current) print
        }
    ')
    if [ -n "$file_summary" ]; then
        printf '%s\n' "$file_summary"
        printf '%s\n' "$file_summary" >> "$coverage_summary"
    fi
done

"$test_python" "$repo_dir/tools/generate_coverage_report.py" \
    --python-results "$python_results" \
    --native-results "$coverage_root/native-tests.log" \
    --coverage-summary "$coverage_summary" \
    --output "$coverage_root/index.html"
printf '\nGraphical coverage report: %s\n' "$coverage_root/index.html"

if [ "$pytest_status" -ne 0 ] || [ "$native_status" -ne 0 ]; then
    exit 1
fi
