import asyncio, json, sys
import websockets
import urllib.request

TARGET_URL = sys.argv[1] if len(sys.argv) > 1 else "http://124.174.108.70/personalized-secure"

async def test():
    uri = "ws://127.0.0.1:8000/ws"
    print(f"Target URL: {TARGET_URL}")
    async with websockets.connect(uri) as ws:
        print("WS connected")
        body = json.dumps({"strategy": "spot_check", "target_url": TARGET_URL}).encode()
        req = urllib.request.Request("http://127.0.0.1:8000/api/tests/run-multi-agent",
            data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"Test started: {result.get('session_id', '?')}")

        events = []
        try:
            for _ in range(60):
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg = json.loads(raw)
                t = msg.get("type", "")
                events.append(t)
                print(f"  WS: {t}")
                if t == "multi_agent:done":
                    break
        except asyncio.TimeoutError:
            print(f"Timeout after {len(events)} events")
        print(f"Total events: {len(events)}")

asyncio.run(test())
