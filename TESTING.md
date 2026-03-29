# BBallVideo Pipeline Test Log

Tracks changes between test runs and their results. Video: Mikey soph (#33, VHHS white/blue) — same ~10min game film for all tests.

---

## test5 (2026-03-28) — First full pipeline run
**Changes**: Initial pipeline with all models integrated
**Config**: ReID threshold 0.6, classifier threshold 0.5, min_distance 3s, basket cooldown 60 frames
**Results**: 23 highlights, 23 stats
**Issues**:
- 43% of all players matched as target (ReID ResNet18 embeddings not discriminative, 0.6 threshold too low)
- Highlights from wrong player and wrong team
- No rebounds or assists detected
- No shot chart (court coords missing)
- Duplicate made_basket events (same basket firing 2-3x)
- Empty metadata on classifier events (no court coords, no action data)

---

## test6 (2026-03-28) — ReID threshold + rebound detection + metadata fixes
**Changes**:
- ReID threshold raised 0.6 → 0.75
- Added rebound detection (ball in_air 15+ frames → new holder)
- Relaxed steal detection: frames_held ≤ 3 (was == 0)
- Improved assist detection: checks last_holder during in_air phase
- Basket cooldown 60 → 180 frames (~6s)
- Fixed classifier event enrichment: store frame_homographies + frame_player_bboxes during loop
- Fixed metadata merge: backfill court_x/court_y from classifier
- Fixed numpy float32 JSON serialization (_sanitize_metadata)
- GPU worker computes missing photo embeddings on-the-fly (_ensure_embedding)
**Config**: ReID threshold 0.75, classifier threshold 0.5, min_distance 3s, basket cooldown 180 frames
**Results**: 2 highlights, 2 stats (both made_basket)
**Issues**:
- 117 merged events → only 2 passed target filter (scorer track IDs didn't match target)
- Neither highlight was the target player or even the right team
- 0 court coords
- Scoring classifier still noisy (116 classifier events)
- Steals/assists/rebounds detected but filtered out (no rescue logic)

---

## test7 (2026-03-28) — Scorer rescue + classifier tuning
**Changes**:
- Scoring classifier threshold 0.5 → 0.7, min_distance 3s → 6s
- _find_scorer_at_frame: widened to ±3s, prefers target tracks
- Added _find_target_near_event rescue for made_baskets (±5s possession check)
- Merge gap raised to 6s
- Persistent possession log for entire video
**Config**: ReID threshold 0.75, classifier threshold 0.7, min_distance 6s
**Results**: 21 highlights, 21 stats (all made_basket)
**Issues**:
- Rescue too aggressive: 19 reassigned (any target possession within ±5s matched)
- 21 baskets for one player in 10 min is impossible — many are opponent baskets
- Still 0 court coords
- Still no steals/assists/rebounds

---

## test8 (2026-03-29) — Tighter rescue filter (in progress)
**Changes**:
- Rescue filter tightened: only fires when target was last_holder while ball in_air (= they shot it)
- OR target held ball within ±1s of event
- Window narrowed ±5s → ±3s
- Added ball_status to possession log
**Config**: ReID threshold 0.75, classifier threshold 0.7, min_distance 6s
**Results**: PENDING
**Expected**: Fewer false reassignments (maybe 2-5 instead of 19)

---

## test9 (planned) — ResNet50 ReID + rescue for all event types + court debugging
**Changes**:
- ReID model: ResNet18 → ResNet50 (resnet50.a2_in1k via timm, 2048-dim embeddings)
- Jersey-only match threshold: 5 reads → 3 reads
- Auto-recompute stale embeddings (512-dim → 2048-dim detection)
- Rescue logic for steals (target as stealer OR victim)
- Rescue logic for assists (target as passer OR scorer)
- Rescue logic for rebounds (target near event ±3s)
- Classifier-only events require ≥ 0.85 confidence
- Classifier dedup within 10s (keep highest conf)
- Steal detection without team classification (proximity-based fallback)
- Assist detection without team classification (proximity-based fallback)
- Court detector debug logging (keypoint count, homography success/fail, reprojection error)

---

## Expected Highlights (ground truth from user)
| Timestamp | Event | Notes |
|-----------|-------|-------|
| 0:50–0:53 | 3pt make | Target player |
| 3:58–4:02 | 2pt make | Target player |
| 5:00–5:03 | 3pt make | Target player |
| 6:31–6:37 | Rebound + assist | Target player |

---

## Key Metrics to Track
- Total events detected (heuristic + classifier)
- Events after target filter
- Reassigned events (rescue logic)
- Target tracks matched (ReID)
- Target match rate (target tracks / total players)
- Court coords populated (count)
- Event type breakdown (made_basket, steal, assist, rebound)
