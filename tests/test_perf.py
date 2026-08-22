import unittest

from omawhy import perf_problems


PS_SAMPLE = """  3.2  1.1 firefox
 92.5  4.0 chrome
 61.0  2.2 python3
  0.0  0.1 sleep
"""

MEMINFO_FULL = "MemTotal: 16000000 kB\nMemAvailable: 1000000 kB\nSwapTotal: 4000000 kB\nSwapFree: 4000000 kB\n"

MEMINFO_OK = "MemTotal: 16000000 kB\nMemAvailable: 8000000 kB\nSwapTotal: 4000000 kB\nSwapFree: 2000000 kB\n"


class FakeUsage:
    def __init__(self, total, used):
        self.total = total
        self.used = used


class PerfProblemsTests(unittest.TestCase):
    def test_names_cpu_hogs_with_severity(self):
        result = perf_problems(ps_output=PS_SAMPLE, loadavg_text="0.10 0.10 0.10 1/1 1",
                               meminfo_text=MEMINFO_OK, temp_output="", disk_usage_fn=lambda p: FakeUsage(100, 10))
        cpu = [p for p in result["problems"] if "CPU" in p["title"] or "using the CPU" in p["title"]]
        self.assertEqual(len(cpu), 2)
        titles = [p["title"] for p in cpu]
        self.assertTrue(any("chrome" in t for t in titles))
        self.assertTrue(any("python3" in t for t in titles))
        self.assertEqual(result["summary"]["error"], 1)  # chrome >= 80%
        self.assertEqual(result["total"], 2)

    def test_flags_memory_pressure(self):
        result = perf_problems(ps_output="", loadavg_text="0.1 0.1 0.1 1/1 1",
                               meminfo_text=MEMINFO_FULL, temp_output="", disk_usage_fn=lambda p: FakeUsage(100, 10))
        self.assertTrue(any(p["title"].startswith(("Memoria", "Memory")) for p in result["problems"]))

    def test_flags_high_temperature(self):
        temps = "temp1_input:        60.000\ntemp2_input:        91.000\n"
        result = perf_problems(ps_output="", loadavg_text="0.1 0.1 0.1 1/1 1",
                               meminfo_text=MEMINFO_OK, temp_output=temps, disk_usage_fn=lambda p: FakeUsage(100, 10))
        hot = [p for p in result["problems"] if "Temperatura" in p["title"] or "temperature" in p["title"]]
        self.assertEqual(len(hot), 1)
        self.assertIn("91", hot[0]["detail"])

    def test_flags_full_disk(self):
        result = perf_problems(ps_output="", loadavg_text="0.1 0.1 0.1 1/1 1",
                               meminfo_text=MEMINFO_OK, temp_output="", disk_usage_fn=lambda p: FakeUsage(100, 95))
        self.assertTrue(any(p["title"].startswith(("Disco", "Disk")) for p in result["problems"]))

    def test_low_battery_names_top_consumers(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            bat = Path(tmp) / "BAT0"
            bat.mkdir()
            (bat / "status").write_text("Discharging")
            (bat / "capacity").write_text("15%\n")
            result = perf_problems(ps_output=PS_SAMPLE, loadavg_text="0.1 0.1 0.1 1/1 1",
                                   meminfo_text=MEMINFO_OK, temp_output="", disk_usage_fn=lambda p: FakeUsage(100, 10),
                                   battery_root=tmp)
            battery = [p for p in result["problems"] if "Batería" in p["title"] or "battery" in p["title"].lower()]
            self.assertEqual(len(battery), 1)
            self.assertIn("chrome", battery[0]["detail"])

    def test_clean_system_reports_zero(self):
        result = perf_problems(ps_output="  1.0  0.5 sleep\n", loadavg_text="0.1 0.1 0.1 1/1 1",
                               meminfo_text=MEMINFO_OK, temp_output="temp1_input: 45.000",
                               disk_usage_fn=lambda p: FakeUsage(100, 30))
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["summary"], {"error": 0, "warning": 0, "info": 0})


if __name__ == "__main__":
    unittest.main()
