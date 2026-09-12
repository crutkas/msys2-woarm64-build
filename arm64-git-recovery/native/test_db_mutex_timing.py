import unittest

from db_channel_checks import expected_mutex_matrix
from db_mutex_timing import summarize
from sources import ContractError


class MutexTimingControls(unittest.TestCase):
    def fixture(self):
        samples, exits = [], []
        for index, (processes, threads, alignment, iterations) in enumerate(expected_mutex_matrix()):
            worker = {"pid": index + 100, "created": (index + 1) * 1_000_000_000,
                      "image": r"C:\owned\test_mutex.exe", "actual_os_threads": threads + 5,
                      "command": f"C:\\owned\\test_mutex.exe -p {processes} -t {threads} -a {alignment} -n {iterations}",
                      "kernel_time_100ns": 10_000, "user_time_100ns": 100_000}
            samples += [{"monotonic": index * 100.0, "workers": [worker]},
                        {"monotonic": index * 100.0 + 99.0, "workers": [worker]}]
            exits.append({"pid": worker["pid"], "created": worker["created"], "raw_exit": 0,
                          "executable": worker["image"]})
        return samples, exits

    def test_all_original_cases_and_exact_generations(self):
        samples, exits = self.fixture()
        cases = summarize(samples, exits)
        self.assertEqual(len(cases), 24)
        self.assertEqual(cases[-1]["configuration"], (4, 4, 128, 2000))
        self.assertEqual(cases[0]["sampled_duration_seconds"], 99)
        self.assertEqual(cases[0]["next_case_start_interval_seconds"], 100)

    def test_missing_case_exit_pid_reuse_and_nonzero_are_not_passes(self):
        samples, exits = self.fixture()
        for bad in (exits[:-1], [{**exits[0], "created": 1}, *exits[1:]],
                    [{**exits[0], "raw_exit": 1460}, *exits[1:]],
                    [{**exits[0], "executable": r"C:\different.exe"}, *exits[1:]]):
            with self.assertRaises(ContractError):
                summarize(samples, bad)
        with self.assertRaises(ContractError):
            summarize(samples[:-2], exits)

    def test_brief_fork_argv_copy_does_not_replace_observed_driver(self):
        samples, exits = self.fixture()
        copied = {**samples[0]["workers"][0], "pid": 999, "created": 999_999_999}
        samples.insert(0, {"monotonic": 0.2, "workers": [copied]})
        cases = summarize(samples, exits)
        self.assertEqual(cases[0]["pid"], 100)
        self.assertEqual(len(cases[0]["observed_candidate_generations"]), 2)


if __name__ == "__main__":
    unittest.main()
