"""Person matting → a transparent-background foreground video, for the
"element behind the subject" effect (text/image sits between the person and the
background).

Uses Robust Video Matting (RVM) — a recurrent video matting model with clean,
temporally-stable hair edges. Reads a video, estimates the person + alpha per
frame (carrying recurrent state for stability), and writes an **alpha WebM**
(VP9 `yuva420p`) of the person over transparency. In Remotion, layer:

    <DynamicVideo src="cut.mp4">     {/* base: background + person */}
      {behindElement}                {/* the thing that goes behind */}
    </DynamicVideo>
    <DynamicVideo src="fg.webm" />   {/* person on top → element sits behind */}

Two back-ends, same output:
  onnx   (default when a model file is found) — onnxruntime + rvm_mobilenetv3_fp32.onnx,
         no PyTorch, loads in a second. Searched in: $PRISMA_RVM_ONNX, ~/.prisma/modelos/rvm/,
         ~/.edvid/modelos/rvm/.  The model is NOT downloaded by this script.
  torch  (fallback / `--backend torch`) — needs the `matting` extra: `uv sync --extra matting`;
         the only path for `--model resnet50`.

Usage:
    python helpers/person_matte.py cut.mp4 -o remotion/public/fg.webm
    python helpers/person_matte.py cut.mp4 -o fg.webm --model resnet50   # higher quality, slower
    python helpers/person_matte.py cut.mp4 -o fg.webm --start 8 --duration 6
"""
from __future__ import annotations

# Windows consoles default to cp1252 and raise UnicodeEncodeError on the arrows
# and box characters these helpers print. Force UTF-8 so a status line can never
# kill a run (measured: transcribe.py + preview_server.py, 2026-08-18).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


import argparse
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # some RVM ops lack MPS kernels

import cv2
import numpy as np


def pick_device(requested: str) -> str:
    import torch
    if requested != "auto":
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


RVM_ONNX_NAMES = ("rvm_mobilenetv3_fp32.onnx", "rvm_mobilenetv3_fp16.onnx")


def find_onnx_model() -> Path | None:
    cands = []
    env = os.environ.get("PRISMA_RVM_ONNX")
    if env:
        cands.append(Path(env))
    for base in (Path.home() / ".prisma" / "modelos" / "rvm", Path.home() / ".edvid" / "modelos" / "rvm"):
        cands += [base / n for n in RVM_ONNX_NAMES]
    return next((c for c in cands if c.is_file()), None)


class OnnxMatter:
    """RVM mobilenetv3 through onnxruntime. Same maths as the torch model: the four
    recurrent states are carried frame to frame; alpha comes back at full size."""

    def __init__(self, model: Path, ratio: float):
        import onnxruntime as ort
        avail = ort.get_available_providers()
        prov = [p for p in ("CUDAExecutionProvider", "DmlExecutionProvider") if p in avail] + ["CPUExecutionProvider"]
        self.sess = ort.InferenceSession(str(model), providers=prov)
        self.provider = self.sess.get_providers()[0]
        self.ratio = np.array([ratio], dtype=np.float32)
        self.rec = [np.zeros((1, 1, 1, 1), dtype=np.float32) for _ in range(4)]
        self.names = [i.name for i in self.sess.get_inputs()]

    def __call__(self, rgb: np.ndarray) -> np.ndarray:
        src = (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        feeds = {self.names[0]: src, self.names[1]: self.rec[0], self.names[2]: self.rec[1],
                 self.names[3]: self.rec[2], self.names[4]: self.rec[3], self.names[5]: self.ratio}
        _fgr, pha, *self.rec = self.sess.run(None, feeds)
        return np.clip(pha[0, 0], 0, 1)


def auto_downsample_ratio(h: int, w: int) -> float:
    # RVM guidance: keep the long side around 512px for HD content.
    return min(512 / max(h, w), 1.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="Matte the person out of a video → alpha WebM (RVM)")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output .webm (VP9 alpha)")
    ap.add_argument("--model", choices=["mobilenetv3", "resnet50"], default="mobilenetv3",
                    help="mobilenetv3 = fast/good (default); resnet50 = best edges, slower")
    ap.add_argument("--backend", choices=["auto", "onnx", "torch"], default="auto",
                    help="auto = onnx when the model file exists and --model is mobilenetv3, else torch")
    ap.add_argument("--device", default="auto", help="torch only: auto | mps | cuda | cpu")
    ap.add_argument("--downsample", type=float, default=None,
                    help="RVM downsample_ratio (default: auto from resolution)")
    ap.add_argument("--start", type=float, default=0.0, help="Start time (s)")
    ap.add_argument("--duration", type=float, default=None, help="Duration (s); default = to end")
    ap.add_argument("--crf", type=int, default=20, help="VP9 quality (lower = better)")
    args = ap.parse_args()

    onnx_model = find_onnx_model() if args.model == "mobilenetv3" else None
    use_onnx = args.backend == "onnx" or (args.backend == "auto" and onnx_model is not None)
    if use_onnx and onnx_model is None:
        sys.exit("sem modelo ONNX do RVM (rvm_mobilenetv3_fp32.onnx) — ponha em ~/.prisma/modelos/rvm/ "
                 "ou defina PRISMA_RVM_ONNX; ou use --backend torch")
    if not use_onnx:
        import torch
        device = pick_device(args.device)
        print(f"backend: torch | device: {device} | model: {args.model}")

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        sys.exit(f"cannot open {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    start_f = int(round(args.start * fps))
    end_f = total if args.duration is None else min(total, start_f + int(round(args.duration * fps)))
    if start_f:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    n_frames = max(0, end_f - start_f)
    ratio = args.downsample if args.downsample is not None else auto_downsample_ratio(H, W)
    print(f"input: {W}x{H} @ {fps:.3f}fps | frames {start_f}..{end_f} ({n_frames}) | downsample_ratio={ratio:.3f}")

    if use_onnx:
        matter = OnnxMatter(onnx_model, ratio)
        print(f"backend: onnx ({matter.provider}) | model: {onnx_model.name}")
    else:
        print("loading RVM model (torch.hub)…")
        model = torch.hub.load("PeterL1n/RobustVideoMatting", args.model, trust_repo=True)
        model = model.eval().to(device)

    # ffmpeg sink: raw RGBA frames → alpha video. ProRes 4444 (.mov) is the
    # reliable alpha format across ffmpeg builds AND is decoded with alpha by
    # Remotion's renderer. VP9/VP8 WebM alpha is lighter but silently drops the
    # alpha channel on some libvpx builds (e.g. Homebrew ffmpeg 8.x) — so .mov
    # is the default. `.webm` is honored if you explicitly ask for it.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() == ".webm":
        codec = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
                 "-b:v", "0", "-crf", str(args.crf)]
        print("warning: encoding VP9 alpha WebM — verify alpha survived (some ffmpeg builds drop it); .mov/ProRes is safer")
    else:
        # ProRes 4444 carries a real alpha plane; qscale ~6 keeps files sane.
        codec = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
                 "-qscale:v", "6"]
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", f"{fps}",
         "-i", "-"] + codec + [str(args.output)],
        stdin=subprocess.PIPE,
    )

    import contextlib
    rec = [None] * 4
    done = 0
    with (contextlib.nullcontext() if use_onnx else torch.no_grad()):
        while done < n_frames:
            ok, bgr = cap.read()
            if not ok:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            if use_onnx:
                a = matter(rgb)                                       # H,W alpha
            else:
                src = torch.from_numpy(rgb).float().div(255.0).permute(2, 0, 1).unsqueeze(0).to(device)
                _fgr, pha, *rec = model(src, *rec, downsample_ratio=ratio)
                a = pha.clamp(0, 1)[0, 0].cpu().numpy()               # H,W alpha
            # Composite the ORIGINAL source RGB (not RVM's decontaminated fgr)
            # with the alpha. The behind-subject effect keeps the SAME background
            # (the base cut), so source pixels make the person seamless over the
            # base with no edge halo; fgr's foreground glow would rim the person.
            rgba = np.dstack([rgb, (a * 255.0)[..., None].astype(np.uint8)])
            ff.stdin.write(rgba.astype(np.uint8).tobytes())
            done += 1
            if done % 60 == 0 or done == n_frames:
                print(f"  matted {done}/{n_frames}", flush=True)

    cap.release()
    ff.stdin.close()
    ff.wait()
    print(f"done: {args.output}  ({done} frames)")


if __name__ == "__main__":
    main()
