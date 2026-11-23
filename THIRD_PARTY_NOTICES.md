# Third-party notices / adoption review (2026-10-29)

## Adopted rhythm library: aubio 0.4.9

- Project/author: aubio project, Paul Brossier and contributors. Keep individual copyright notices in bundled sources.
- Source: https://aubio.org/ ; https://pypi.org/project/aubio/0.4.9/ ; https://github.com/aubio/aubio
- License: GNU GPL version 3 or (at your option) any later version.
- Full license: `docs/licenses/aubio-GPL-3.0.txt` and `third_party/aubio/COPYING`.
- Complete modified source included in `third_party/aubio/`, with all upstream notices retained.
- Local modification: two NumPy ufunc callback signatures are const-qualified in `python/ext/ufuncs.c` for modern clang/NumPy; no rhythm algorithm changes. See `AINOTE-CHANGES.md` in that directory.
- No pretrained models used. Runtime audio stays local; no SaaS/API account or usage fee.

Private local use and modification do not require publishing your private application source. GPL does not prohibit commercial use. If distributing the combined application, plan GPL-compatible distribution of the covered combined work, license/copyright notices and corresponding source including build materials. Merely including this notice or a link to upstream is not a substitute for all GPL obligations. No decision to publish or relicense the user's entire project has been made here. The bundled third-party source retains its own license.

## Other runtime dependencies

The environment includes NumPy (BSD-3-Clause), sounddevice (MIT), SoundFile (BSD-3-Clause; bundled libsndfile has LGPL terms), PySide6 Essentials/shiboken6 (Qt for Python's LGPL/GPL/commercial licensing choices), cffi (MIT), pycparser (BSD), typing_extensions (PSF-2.0). Their installed distribution metadata and accompanying license files are retained. A packaged release must retain those notices and satisfy applicable Qt/LGPL and binary-library conditions; this development setup is not a finished redistribution package. No optional Qt WebEngine/PDF/Addons are required by the application.

## Candidates not shipped

- BeatNet: repository license CC-BY-4.0; author attribution/license link/change marking apply. Its own license does not remove requirements of dependencies. Upstream runtime imports madmom, torch, librosa, PyAudio and others. Deferred in this change because of integration and environment cost; no runtime accuracy claim or speed ranking is made for BeatNet. The madmom import alone does not imply that BeatNet uses madmom's noncommercial model files. BeatNet model provenance/licensing must be reviewed separately before shipping weights.
- madmom: code BSD-2-Clause; supplied model/data files CC-BY-NC-SA-4.0. Default model-based use is therefore not treated as commercially unrestricted. Deferred; no models downloaded or bundled.
- librosa: ISC; copyright/license notices must accompany copies. Suitable for offline reference analysis. `beat_track` is not a ready-made causal streaming tracker, so it was not adopted as the live backend or benchmarked as if equivalent.

Primary references: 
- https://raw.githubusercontent.com/aubio/aubio/master/README.md
- https://raw.githubusercontent.com/aubio/aubio/master/COPYING
- https://raw.githubusercontent.com/mjhydri/BeatNet/main/LICENSE
- https://raw.githubusercontent.com/mjhydri/BeatNet/main/setup.py
- https://raw.githubusercontent.com/mjhydri/BeatNet/main/src/BeatNet/BeatNet.py
- https://raw.githubusercontent.com/CPJKU/madmom/main/LICENSE
- https://raw.githubusercontent.com/librosa/librosa/main/LICENSE.md

## Adopted AI: Beat This! 1.1.0, checkpoints small0 and small1

- Authors: Francesco Foscarin, Jan Schlüter, Gerhard Widmer; Institute of Computational Perception, JKU Linz, Austria (2024).
- Code: https://github.com/CPJKU/beat_this ; package beat-this 1.1.0.
- Code and published model weights are expressly MIT licensed in upstream README, License section: https://github.com/CPJKU/beat_this#license . A snapshot is retained in `work/ai/beat-this-README.txt`; license in `docs/licenses/beat-this-MIT.txt`.
- Models downloaded unchanged from the official cloud URL documented by upstream. Exact URLs, SHA-256 hashes, server SHA-1 values, sizes and attribution are recorded in `models/manifest.json`.
- The MIT copyright/permission/disclaimer must accompany copies of the code and weights. Do not imply author endorsement.
- Local adaptation is our past-window inference and consensus/clock logic in `ainote/ai_tracking.py`; upstream code and weight files were not modified. This is not an official causal-streaming variant of Beat This!.
- No madmom package, madmom model files or DBN decoder are used by this AI backend (`dbn=False`).

Additional execution dependencies are PyTorch 2.8.0 (BSD-style with bundled third-party notices), torchaudio 2.8.0 (BSD-2-Clause), einops (MIT), rotary-embedding-torch (MIT), soxr (LGPL-2.1-or-later plus its upstream notices), and their resolved dependencies. Installed license materials were copied to `docs/licenses/ai-runtime/` and remain in the Python environment. `requirements.lock.txt` records exact versions. The prior aubio GPL and Qt/LGPL conditions still apply; adding MIT AI does not remove them. This task did not create or publish a redistributable application package.

### Audio, privacy, and training-material limits

Runtime inference is local and does not upload, persist or republish incoming audio. Model installation explicitly contacts the official artifact hosts; application startup uses local checkpoints only. Benchmarks use our generated synthetic accompaniment, not downloaded karaoke recordings, scraped music, DRM circumvention or third-party training audio. No new model training was performed.

The upstream README notes that some training recordings have copyright or limited Creative Commons terms and leaves the impact on a use case to the user. The published MIT model grant is documented here; it is not proof of rights clearance for every underlying training recording, nor a warranty of every legal question. Input music and any future recording, public performance, distribution or commercial release have their own rights requirements, separate from the software/model license. Only use input audio you may lawfully use in the intended setting. No external distribution or public release has been performed in this task.

### Other AI candidates

BeatNet's repository publishes CC-BY-4.0 terms but has a heavier madmom/PyAudio integration path. BeatNet+ did not expose a LICENSE in the reviewed root listing; we did not infer permission from public visibility. Neither was installed or bundled. Actual inference comparison in this change is between the two independently trained Beat This! checkpoints, not a claimed runtime benchmark against BeatNet/BeatNet+.
