# TrueNAS Server GPU Install Checklist

Server: Lenovo 11AAS0Q900 / Ryzen 5 PRO 2400G / 32GB RAM

## 1. Which slot has the eSATA card?
- Open the case and look at which PCIe slot the eSATA (ASMedia ASM1062) card is in
- If it's in the x16 slot (the longest one), it can be moved to any smaller slot — eSATA only needs x1
- The GPU needs the x16 slot

## 2. PSU Wattage
- Find the sticker on the power supply (usually on the side)
- Look for "Max Output", "Total Power", or "Output" in watts
- **If 300W+**: RTX 3060 12GB is an option (needs ~170W + 8-pin power cable)
- **If under 300W**: Go with Tesla T4 or RTX A2000 (only 70W, no extra cables needed)
- **If under 180W**: You'll need to replace the PSU too — probably not worth it

## 3. Physical Clearance
- Measure from the back bracket of the x16 slot to the nearest obstruction (drive cage, cables, opposite wall)
- **Full-size GPU (RTX 3060)**: needs ~10-11 inches (267mm)
- **Low-profile GPU (T4 / A2000)**: needs ~6-7 inches (168mm) — fits almost anywhere
- Also check height — low-profile cards are about 2.7 inches tall, full-size are ~4.5 inches

## 4. PCIe Power Connectors
- Look for unused cables coming from the PSU with 6-pin or 8-pin connectors
- The Tesla T4 and RTX A2000 do NOT need these (slot powered only)
- The RTX 3060 needs one 8-pin connector — if your PSU doesn't have one, you'd need a SATA-to-8-pin adapter (not ideal) or a PSU upgrade

## 5. Case Airflow
- Is there a fan near the PCIe area?
- GPU will add heat — especially in a system already running 24/7 with drives

---

## GPU Recommendations (in order of preference for this build)

| GPU | VRAM | Power | External Power? | Approx Used Price | Notes |
|-----|------|-------|-----------------|-------------------|-------|
| Tesla T4 | 16 GB | 70W | No | $150-200 | Best bang for buck. Headless (no video out). Perfect for inference server. |
| RTX A2000 12GB | 12 GB | 70W | No | $250-300 | Low-profile, slot powered. Has video out if you ever want it. |
| RTX 3060 12GB | 12 GB | 170W | Yes (1x 8-pin) | $200-250 | Best perf/dollar but needs PSU headroom and power cable. |
| Tesla P40 | 24 GB | 250W | Yes (1x 8-pin) | $200-250 | Massive VRAM but loud, hot, needs big PSU. Overkill. |

## Quick Decision Tree

```
Is the x16 slot available (or can you move eSATA)?
  No  → Stop. No GPU option without a different motherboard.
  Yes ↓

Is PSU 300W or more?
  Yes → RTX 3060 12GB (best performance, check for 8-pin cable)
  No  ↓

Is PSU at least 180W?
  Yes → Tesla T4 (best option — 70W, no cables, 16GB VRAM)
  No  → PSU replacement needed first, probably not worth it
```

## Storage Architecture

All video storage uses the local TrueNAS filesystem instead of S3/Cloudflare R2. Raw uploads and generated clips are stored under the `STORAGE_BASE_PATH` mount point (e.g., `/mnt/bball-video`). This keeps data on-premises with no cloud egress costs. Current allocation is 1TB — monitor usage as game footage accumulates.

## After Install
- TrueNAS may need GPU passthrough configured if running inference in a VM/container
- Verify NVIDIA drivers: `nvidia-smi` should show the card
- CUDA toolkit needed for PyTorch/YOLO
