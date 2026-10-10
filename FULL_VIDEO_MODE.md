# Continuous video generation (single-pass)

All normalized source frames are generated in **one ComfyUI prompt**, without
splitting or identity-breaking boundaries. Input is normalized to 16 FPS.
The model receives a 4n+1 length (minimum 17) padded with cloned end frames;
the output is trimmed to the exact original frame count and source audio is
restored. There is no configured maximum duration or frame count.

**Important:** removing software limits does not remove GPU VRAM limits.
Long clips may fail with CUDA OOM, take hours, or exceed Vast request timeouts.
We intentionally do **not** silently fall back to chunks after OOM.

R2 status snapshots are cached by the local UI. During cold start the UI
checks R2 at most once per 60 seconds per job (shared across browser tabs);
after startup it checks at most once per 10 seconds. Sampling percentages
refer only to the current sampler, not overall end-to-end progress.

Stopping a Vast endpoint or destroying a worker instance is **not** performed
by the worker: endpoint/workergroup ownership and pending requests must be
verified first. Configure Vast Serverless scale-to-zero/idle worker policy
where supported; never terminate shared GPU capacity from a request handler.

Lip-sync is not audio-conditioned in the current Bernini RV2V workflow.
Evaluate a separate audio-driven mouth refinement pass on a short sample
before integrating it into production.
