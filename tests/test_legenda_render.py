"""Pixel regression for a real HyperFrames render.

Set PRISMA_TEST_HYPERFRAMES=1 to run with the pinned CLI, Chromium and FFmpeg.
"""
from __future__ import annotations

import json
import os
import subprocess

import numpy as np
import pytest
from PIL import Image

from test_cenas import _caps

pytestmark = pytest.mark.skipif(
    os.environ.get("PRISMA_TEST_HYPERFRAMES") != "1",
    reason="set PRISMA_TEST_HYPERFRAMES=1 with HyperFrames installed to check rendered pixels",
)


def test_legenda_mista_renders_red_strike_only_from_negation_pair_end(tmp_path):
    import cenas

    source = tmp_path / "plain.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=0x333333:s=540x960:d=5:r=30",
         "-f", "lavfi", "-i", "anullsrc", "-shortest", "-pix_fmt", "yuv420p", str(source)],
        check=True,
    )
    captions = _caps(tmp_path)
    words = json.loads(captions.read_text(encoding="utf-8"))
    words.extend([
        {"text": "não", "startMs": 3970, "endMs": 4100},
        {"text": "funciona", "startMs": 4100, "endMs": 4300},
    ])
    captions.write_text(json.dumps(words), encoding="utf-8")
    project = cenas.build("legenda", {
        "video": str(source), "de": 0.0, "ate": 5.0,
        "legendas": str(captions), "estilo": "mista", "destaques": ["funciona"],
    }, tmp_path / "hyperframes")
    video = cenas.render(project)

    def red_pixels_at(seconds, crop):
        frame = tmp_path / "frame.png"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", str(seconds), "-i", str(video), "-frames:v", "1", str(frame)],
            check=True,
        )
        with Image.open(frame) as image:
            r, g, b = np.asarray(image.convert("RGB").crop(crop), dtype=np.int16).transpose(2, 0, 1)
        return np.count_nonzero((r > 170) & (r - g > 130) & (r - b > 125))

    same_line = (310, 860, 540, 1000)  # "não é", below the red word "carro"
    assert red_pixels_at(1.30, same_line) == 0  # the second word ends at 1.40 s
    assert red_pixels_at(1.70, same_line) > 1000
    assert red_pixels_at(2.45, same_line) == 0  # next caption block

    # A highlighted second word occupies its own line. Both words need a strike.
    assert red_pixels_at(4.50, (470, 710, 610, 760)) > 500  # "não"
    assert red_pixels_at(4.50, (195, 770, 885, 900)) > 1000  # "funciona"
