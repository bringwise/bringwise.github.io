#!/usr/bin/env python3
"""
Remove the "SoBrief.com" watermark from book cover images.

The watermark is a fixed, semi-transparent text stamp in the top-right corner.
This tool loads a pre-built letter-shape mask (tools/sobrief_mask.png) and uses
OpenCV inpainting to paint over ONLY the letter pixels, so the surrounding
background/artwork is preserved (much cleaner than blanking the whole corner).

Only 480-pixel-wide covers carry the watermark; any other size is skipped and
reported (a handful of covers come from a different source without a stamp).

Usage
-----
  # Preview a few before/after comparisons (writes PNGs, changes nothing):
  python tools/remove_sobrief_watermark.py --preview 8

  # Dry run over the whole folder (reports what WOULD change):
  python tools/remove_sobrief_watermark.py --dry-run

  # Clean every cover in place (repo is git-tracked -> easy to revert):
  python tools/remove_sobrief_watermark.py --in-place

  # Or write cleaned copies to a separate folder, leaving originals untouched:
  python tools/remove_sobrief_watermark.py --out books_clean

  # Rebuild the mask from the corpus (only needed if the watermark changes):
  python tools/remove_sobrief_watermark.py --build-mask
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MASK_PATH = os.path.join(HERE, "sobrief_mask.png")

# Watermark region for a 480-wide reference cover (x0, y0, x1, y1).
# The mask PNG is exactly (y1-y0) x (x1-x0). Coordinates are anchored to the
# top-right, so they hold for both 480x720 and 480x715 covers.
REGION = (330, 8, 478, 42)
REF_WIDTH = 480

INPAINT_RADIUS = 5
WEBP_QUALITY = 95  # re-encode quality for the whole image


# --------------------------------------------------------------------------- #
# Unicode-safe image IO (cv2.imread/imwrite choke on non-ASCII paths on Windows)
# --------------------------------------------------------------------------- #
def imread_u(path: str):
    try:
        buf = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


def imwrite_u(path: str, img, ext: str = ".webp", quality: int = WEBP_QUALITY) -> bool:
    params = []
    if ext.lower() == ".webp":
        params = [cv2.IMWRITE_WEBP_QUALITY, quality]
    elif ext.lower() in (".jpg", ".jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        return False
    buf.tofile(path)
    return True


# --------------------------------------------------------------------------- #
# Mask handling
# --------------------------------------------------------------------------- #
def load_mask():
    m = cv2.imread(MASK_PATH, cv2.IMREAD_GRAYSCALE)
    if m is None:
        sys.exit(f"ERROR: mask not found at {MASK_PATH}. Run with --build-mask first.")
    return m


def build_full_mask(img_shape, master_mask):
    """Place (and scale if needed) the master mask into a full-image mask."""
    h, w = img_shape[:2]
    s = w / REF_WIDTH
    x0, y0, x1, y1 = (int(round(v * s)) for v in REGION)
    x1 = min(x1, w)
    y1 = min(y1, h)
    rw, ry = x1 - x0, y1 - y0
    if rw <= 0 or ry <= 0:
        return None
    m = master_mask
    if s != 1.0:
        m = cv2.resize(master_mask, (REGION[2] - REGION[0], REGION[3] - REGION[1]))
    m = cv2.resize(m, (rw, ry), interpolation=cv2.INTER_NEAREST)
    full = np.zeros((h, w), np.uint8)
    full[y0:y1, x0:x1] = m
    return full


def clean_image(img, master_mask):
    full = build_full_mask(img.shape, master_mask)
    if full is None:
        return img
    return cv2.inpaint(img, full, INPAINT_RADIUS, cv2.INPAINT_TELEA)


def is_watermarked(img) -> bool:
    """Only 480-wide covers carry the watermark stamp."""
    return img is not None and img.shape[1] == REF_WIDTH


# --------------------------------------------------------------------------- #
# Mask builder (regenerates the master mask from the corpus)
# --------------------------------------------------------------------------- #
def build_mask(files):
    rx0, ry0, rx1, ry1 = REGION
    acc = None
    n = 0
    for f in files[::3]:
        im = imread_u(f)
        if im is None or im.shape[1] != REF_WIDTH:
            continue
        g = cv2.cvtColor(im[ry0:ry1, rx0:rx1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        mg = np.sqrt(gx * gx + gy * gy)
        acc = mg if acc is None else acc + mg
        n += 1
    if acc is None:
        sys.exit("ERROR: no 480-wide images found to build a mask from.")
    m = acc / acc.max()
    mask = (m > 0.15).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    cv2.imwrite(MASK_PATH, mask)
    print(f"Built mask from {n} images -> {MASK_PATH} (shape {mask.shape})")


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #
def preview(files, master_mask, count, out_png):
    picks = files[:: max(1, len(files) // count)][:count]
    rows = []
    for f in picks:
        im = imread_u(f)
        if not is_watermarked(im):
            continue
        out = clean_image(im, master_mask)
        a, b = im[0:60, 240:480], out[0:60, 240:480]
        sep = np.full((60, 6, 3), (0, 0, 255), np.uint8)
        rows.append(np.hstack([a, sep, b]))
        rows.append(np.full((6, a.shape[1] * 2 + 6, 3), 200, np.uint8))
    if not rows:
        print("No watermarked images to preview.")
        return
    grid = np.vstack(rows)
    grid = cv2.resize(grid, (grid.shape[1] * 2, grid.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(out_png, grid)
    print(f"Wrote preview (left=original | right=cleaned) -> {out_png}")


# --------------------------------------------------------------------------- #
# Main processing
# --------------------------------------------------------------------------- #
def process_one(f, master_mask, out_dir, in_place, dry_run, quality):
    im = imread_u(f)
    if im is None:
        return ("error", f)
    if not is_watermarked(im):
        return ("skipped", f)
    if dry_run:
        return ("would-clean", f)
    out = clean_image(im, master_mask)
    ext = os.path.splitext(f)[1] or ".webp"
    if in_place:
        dst = f
    else:
        os.makedirs(out_dir, exist_ok=True)
        dst = os.path.join(out_dir, os.path.basename(f))
    if imwrite_u(dst, out, ext, quality):
        return ("cleaned", f)
    return ("error", f)


def main():
    ap = argparse.ArgumentParser(description="Remove the SoBrief.com watermark from book covers.")
    ap.add_argument("--dir", default="books", help="folder of images (default: books)")
    ap.add_argument("--glob", default="*.webp", help="filename pattern (default: *.webp)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--in-place", action="store_true", help="overwrite originals (repo is git-tracked)")
    group.add_argument("--out", metavar="DIR", help="write cleaned copies to DIR instead")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    ap.add_argument("--preview", type=int, metavar="N", help="write N before/after comparisons and exit")
    ap.add_argument("--build-mask", action="store_true", help="rebuild the master mask from the corpus")
    ap.add_argument("--quality", type=int, default=WEBP_QUALITY, help=f"webp quality (default {WEBP_QUALITY})")
    ap.add_argument("--workers", type=int, default=min(8, (os.cpu_count() or 4)), help="parallel workers")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, args.glob)))
    if not files:
        sys.exit(f"No files match {os.path.join(args.dir, args.glob)}")

    if args.build_mask:
        build_mask(files)
        return

    master_mask = load_mask()

    if args.preview is not None:
        out_png = os.path.join(args.dir, "..", "watermark_preview.png")
        out_png = os.path.abspath(out_png)
        preview(files, master_mask, args.preview, out_png)
        return

    if not args.in_place and not args.out and not args.dry_run:
        sys.exit("Choose an output mode: --in-place, --out DIR, or --dry-run.")

    print(f"{len(files)} files | mode: "
          f"{'DRY-RUN' if args.dry_run else ('in-place' if args.in_place else 'out=' + args.out)}")

    counts = {"cleaned": 0, "skipped": 0, "error": 0, "would-clean": 0}
    skipped, errors = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process_one, f, master_mask, args.out, args.in_place, args.dry_run, args.quality)
                for f in files]
        for i, fut in enumerate(as_completed(futs), 1):
            status, f = fut.result()
            counts[status] += 1
            if status == "skipped":
                skipped.append(f)
            elif status == "error":
                errors.append(f)
            if i % 200 == 0 or i == len(files):
                done = counts["cleaned"] + counts["would-clean"]
                print(f"  {i}/{len(files)}  processed={done}  skipped={counts['skipped']}  errors={counts['error']}")

    print("\n--- summary ---")
    for k, v in counts.items():
        if v:
            print(f"  {k}: {v}")
    if skipped:
        print("  skipped (no watermark / wrong size):")
        for f in skipped:
            print(f"    - {os.path.basename(f)}")
    if errors:
        print("  ERRORS:")
        for f in errors:
            print(f"    - {os.path.basename(f)}")


if __name__ == "__main__":
    main()
