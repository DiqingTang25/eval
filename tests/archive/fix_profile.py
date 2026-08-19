#!/usr/bin/env python3
"""修复 platform_profile.json 指向有效的 schema"""
import os, yaml, json, glob

base = "/opt/agent_eval"
probe = os.path.join(base, "output", "platform_probe")
profile_path = os.path.join(probe, "platform_profile.json")

# 找最新的有效 schema
valid = []
for d in glob.glob(os.path.join(probe, "*/")):
    sf = os.path.join(d, "platform_schema.yaml")
    if os.path.exists(sf):
        data = yaml.safe_load(open(sf))
        phases = len(data.get("structure", {}).get("phases", []))
        if phases > 0:
            mtime = os.path.getmtime(sf)
            valid.append((mtime, sf, phases, os.path.basename(d.rstrip("/"))))

if valid:
    valid.sort(reverse=True)
    best = valid[0]
    print(f"最新有效 schema: {best[3]} (phases={best[2]})")

    # 更新 profile
    profile = json.loads(open(profile_path).read()) if os.path.exists(profile_path) else {}
    profile["schema_path"] = best[1]
    profile["phases_found"] = best[2]
    profile["schema_valid"] = True
    profile["available"] = True
    json.dump(profile, open(profile_path, "w"), indent=2, ensure_ascii=False)
    print(f"Profile 已更新: phases_found={best[2]}")
else:
    print("无有效 schema!")
