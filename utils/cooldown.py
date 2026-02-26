import time

COOLDOWN = {}

def allow(key: str, seconds: int) -> bool:
    now = time.time()
    last = COOLDOWN.get(key, 0)

    if now - last < seconds:
        return False

    COOLDOWN[key] = now

    if len(COOLDOWN) > 5000:
        for k, v in list(COOLDOWN.items()):
            if now - v > seconds * 2:
                COOLDOWN.pop(k, None)

    return True
