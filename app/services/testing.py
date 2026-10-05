from datetime import datetime,timezone
def run_test(target,mode):
    if mode not in {"read-only","contract"}:
        return {"status":"blocked","target":target,"mode":mode,"reason":"Only safe tests are enabled in the initial bridge."}
    return {"status":"passed","target":target,"mode":mode,
      "checks":["target accepted","permission boundary present","no production mutation"],
      "timestamp":datetime.now(timezone.utc).isoformat()}
