import asyncio, json
import websockets
import urllib.request

async def test():
    # Test 1: Connect WS through nginx (/test/ws)
    uri = "ws://127.0.0.1/test/ws"
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri) as ws:
        print("WS connected through nginx")

        # Test 2: Start Multi-Agent through nginx
        req = urllib.request.Request(
            "http://127.0.0.1/test/api/tests/run-multi-agent",
            data=json.dumps({"strategy": "spot_check"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"Test started: {result.get('session_id', '?')}")

        # Test 3: Receive WS events
        events = []
        try:
            for _ in range(40):
                raw = await asyncio.wait_for(ws.recv(), timeout=1.5)
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
