import sys, time
sys.path.insert(0, ".")
from src.platform_probe.explorer import PlatformExplorer
from pathlib import Path

od = Path("/opt/agent_eval/output/platform_probe/evo_test")
od.mkdir(parents=True, exist_ok=True)

explorer = PlatformExplorer(headless=True, output_dir=od, max_depth=3, max_pages=50, verbose=False)
schema, report, yaml_path = explorer.explore(
    target_url="http://124.174.108.70/personalized-secure",
    username="111", password="123456")

print(f"Steps: {report.steps_found}, Phases: {report.phases_found}, APIs: {report.api_endpoints_found}, Conf: {report.confidence.overall:.0%}")
