"""从源图里抠出内部的「带 K 聊天气泡」，去掉外层圆角方形边框。

用法：

    E:\\Agent\\develop\\miniconda3\\envs\\benzhubenzhu\\python.exe frontend/scripts/extract_bubble_logo.py

产物（写入 `frontend/public/logo/`）：

    logo-bubble-128.png   128x128   登录页
    logo-bubble-64.png     64x64   主界面侧边栏
    logo-bubble-32.png     32x32   浏览器标签页
    favicon.ico         16/32/48   浏览器标签页（由气泡生成）

## 为什么这里**不用** rembg

需求里建议用 rembg，但它解决不了这个问题，原因不是精度而是**任务类型不匹配**：

rembg 用的是 u2net 这类**显著目标分割**模型——输入一张图，输出「画面主体」的 alpha。
而这张图的画面主体恰恰是**整个圆角方框**；气泡是方框内部的一个细节。
模型没有任何依据能知道我们要的是「方框里面那个气泡」而不是「方框」。
换句话说，即便 rembg 跑得完美，它给出的也会是圆角方框的轮廓。

更关键的是，气泡与方框**之间不存在可供分割的颜色/亮度差异**：
两者同属蓝色系，而且方框底部的高光比气泡内部还亮（实测方框底部同样是亮青色）。
任何按颜色或亮度做前景/背景分离的方法都会在这里失效。

真正能把两者分开的信号只有一个：气泡那条**比紧邻区域更亮的细轮廓线**。
所以本脚本用「局部对比度脊线 + 洪泛填充」——这是几何/结构方法，
不是分割模型能替代的，因此没有引入 rembg（也避免为它下载约 176MB 权重）。

## 算法四步

1. **脊线提取**：`原图亮度 - 高斯模糊(亮度)` 得到局部对比度，超过阈值的像素即轮廓线。
   用局部对比度而不是绝对亮度，是为了不受「背景本身有多亮」影响。
2. **洪泛找内部**：在「非脊线」掩码上取连通域。种子在轮廓半径内侧 80% 处撒 24 个方向，
   逐个验证（面积不能铺满整图、最大半径要合理），挑出真正被轮廓圈住的那一块。
   单一中心种子不可靠——图像正中心恰好落在字母 K 的笔画上。
3. **补回轮廓并填洞**：把与内部相邻的脊线连通域并入，再 `fill_holes`
   把 K 自身轮廓线留下的缝隙补上。
4. **羽化 + 预乘缩放**：alpha 轻微羽化以免阈值边界呈锯齿；缩小时先乘 alpha 再重采样，
   否则透明区的颜色会混进边缘形成光晕。

## 一个反直觉之处

分析用的分辨率（1024）与输出用的分辨率（源图 2048）不同：掩码是一个低频的几何形状，
在 1024 上算完再上采样到源图尺寸，边界误差小于 1px，在最终 128px 的成品上完全不可见；
好处是阈值参数与源图分辨率解耦，换一张更大或更小的源图不用重新调参。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "public" / "logo"
SOURCE = OUTPUT_DIR / "logo.jpg"

# 掩码分析用的工作分辨率（与源图分辨率解耦，见模块 docstring 末尾说明）
WORK_SIZE = 1024

# 1) 脊线参数。sigma 是估计「局部背景」的高斯半径，必须明显大于轮廓线宽
#    （轮廓约 3-5px），否则轮廓本身会被当成背景而被减掉。
RIDGE_SIGMA = 6.0
RIDGE_THRESHOLD = 15.0

# 2) 种子环半径：相对轮廓半径的比例。取 0.80 是为了落在气泡内部、
#    又尽量避开中心的字母 K。
SEED_RADIUS_RATIO = 0.80
SEED_COUNT = 24

# 气泡轮廓半径约为图幅的 0.348（第一轮实测 r(θ) 均值）
EXPECTED_RADIUS_RATIO = 0.348

# 候选连通域的有效区间：面积占比上限、最大半径相对图幅的区间。
# 圆的面积占比 = π × 0.348² ≈ 38%；下界放宽到 0.30 是为了容纳左下角的尾巴。
AREA_MAX_PERCENT = 40.0
RADIUS_MIN_RATIO = 0.30
RADIUS_MAX_RATIO = 0.48

# 3) alpha 羽化半径（在工作分辨率上，约 0.1% 图幅）
FEATHER_SIGMA = 1.0

PNG_SIZES = (128, 64, 32)
ICO_SIZES = ((16, 16), (32, 32), (48, 48))


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec.601 亮度。"""
    return rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def build_bubble_mask(rgb_work: np.ndarray) -> tuple[np.ndarray, str]:
    """在当前分辨率上求出气泡掩码（bool 数组）。"""
    height, width = rgb_work.shape[:2]
    lum = luminance(rgb_work)

    # --- 第 1 步：局部对比度脊线 -------------------------------------------------
    local_background = ndimage.gaussian_filter(lum, sigma=RIDGE_SIGMA)
    ridge = (lum - local_background) > RIDGE_THRESHOLD
    if not ridge.any():
        raise SystemExit("没有检测到任何脊线，请调低 RIDGE_THRESHOLD。")

    # --- 第 2 步：在非脊线区域洪泛，用多个种子挑出被轮廓圈住的那一块 ------------
    labels, _ = ndimage.label(~ridge)
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
    radius_ref = EXPECTED_RADIUS_RATIO * width

    candidates: list[tuple[int, float, float]] = []
    for index in range(SEED_COUNT):
        theta = 2.0 * np.pi * index / SEED_COUNT
        sx = int(round(cx + SEED_RADIUS_RATIO * radius_ref * np.cos(theta)))
        sy = int(round(cy + SEED_RADIUS_RATIO * radius_ref * np.sin(theta)))
        if not (0 <= sx < width and 0 <= sy < height):
            continue
        label_id = int(labels[sy, sx])
        if label_id == 0:  # 种子正好落在脊线上
            continue
        region = labels == label_id
        area_percent = float(region.mean() * 100.0)
        ys, xs = np.nonzero(region)
        radius_max = float(np.hypot(xs - cx, ys - cy).max() / width)
        candidates.append((label_id, area_percent, radius_max))

    if not candidates:
        raise SystemExit("所有候选种子都落在脊线上，无法确定气泡内部。")

    valid = [
        c
        for c in candidates
        if c[1] < AREA_MAX_PERCENT and RADIUS_MIN_RATIO < c[2] < RADIUS_MAX_RATIO
    ]
    if not valid:
        detail = "  ".join(f"label={c[0]} area={c[1]:.1f}% r_max={c[2]:.3f}" for c in candidates[:6])
        raise SystemExit(
            "没有任何候选连通域被轮廓圈住——说明该阈值下气泡轮廓不闭合。\n"
            f"候选：{detail}\n"
            "可尝试调低 RIDGE_THRESHOLD（当前 "
            f"{RIDGE_THRESHOLD}）。"
        )

    # 面积最大的那个有效候选即气泡内部（其余是被轮廓分隔开的小碎块）
    label_id, area_percent, radius_max = max(valid, key=lambda c: c[1])
    interior = labels == label_id
    note = f"内部连通域 area={area_percent:.2f}% r_max/w={radius_max:.3f}"

    # --- 第 3 步：并入轮廓线本身，再填补内部孔洞 --------------------------------
    ridge_labels, _ = ndimage.label(ridge)
    ring_seed = ridge & ndimage.binary_dilation(interior, iterations=1)
    ring_ids = np.unique(ridge_labels[ring_seed])
    ring_ids = ring_ids[ring_ids > 0]
    ring = np.isin(ridge_labels, ring_ids)

    bubble = ndimage.binary_fill_holes(interior | ring)

    # 只保留与中心相连的那一块，避免零散碎片。中心可能落在脊线上，
    # 此时退回到面积最大的一块。
    components, _ = ndimage.label(bubble)
    center_label = int(components[int(round(cy)), int(round(cx))])
    if center_label == 0:
        sizes = ndimage.sum(bubble, components, range(1, components.max() + 1))
        center_label = int(np.argmax(sizes)) + 1
    bubble = ndimage.binary_fill_holes(components == center_label)

    note += f"  轮廓环={ring.mean() * 100:.2f}%  最终={bubble.mean() * 100:.2f}%"
    return bubble, note


def build_alpha(mask: np.ndarray, sigma: float) -> np.ndarray:
    """把布尔掩码变成 0..1 的 alpha，并轻微羽化以消除阈值锯齿。"""
    alpha = mask.astype(np.float32)
    if sigma > 0:
        alpha = ndimage.gaussian_filter(alpha, sigma=sigma)
        low, high = float(alpha.min()), float(alpha.max())
        if high > low:
            alpha = (alpha - low) / (high - low)
    return np.clip(alpha, 0.0, 1.0)


def trim_to_content(image: Image.Image, threshold: int = 8) -> Image.Image:
    """裁掉四周全透明的区域。"""
    solid = image.getchannel("A").point(lambda value: 255 if value > threshold else 0)
    box = solid.getbbox()
    if box is None:
        raise SystemExit("裁剪失败：整张图都是透明的。")
    return image.crop(box)


def pad_to_square(image: Image.Image) -> Image.Image:
    """补成正方形（透明填充）。直接缩放到方形会把不方的图拉伸变形。"""
    width, height = image.size
    side = max(width, height)
    if (width, height) == (side, side):
        return image
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - width) // 2, (side - height) // 2), image)
    return canvas


def resize_premultiplied(image: Image.Image, size: int) -> Image.Image:
    """预乘 alpha 后 LANCZOS 缩放，避免透明区颜色混入边缘形成光晕。"""
    array = np.asarray(image, dtype=np.float32)
    alpha = array[..., 3:4] / 255.0
    array[..., :3] *= alpha

    premultiplied = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), "RGBA")
    resized = premultiplied.resize((size, size), Image.LANCZOS)

    out = np.asarray(resized, dtype=np.float32)
    out_alpha = out[..., 3:4]
    divisor = np.where(out_alpha > 0, out_alpha / 255.0, 1.0)
    out[..., :3] = np.clip(out[..., :3] / divisor, 0, 255)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(f"找不到源图：{SOURCE}")

    with Image.open(SOURCE) as opened:
        source_size = opened.size
        source_rgb = opened.convert("RGB")

    # 在较低分辨率上算掩码（更快、与源图分辨率解耦），再上采样回源图尺寸
    work = source_rgb.resize((WORK_SIZE, WORK_SIZE), Image.LANCZOS)
    mask_work, note = build_bubble_mask(np.asarray(work, dtype=np.float32))
    print(f"源图        : {SOURCE.name}  {source_size[0]}x{source_size[1]}")
    print(f"掩码（{WORK_SIZE}）: {note}")

    alpha_work = build_alpha(mask_work, FEATHER_SIGMA)
    alpha_work_img = Image.fromarray((alpha_work * 255).astype(np.uint8), "L")
    alpha_source = np.asarray(alpha_work_img.resize(source_size, Image.LANCZOS), dtype=np.float32)

    extracted = source_rgb.convert("RGBA")
    extracted.putalpha(Image.fromarray(np.clip(alpha_source, 0, 255).astype(np.uint8), "L"))

    trimmed = trim_to_content(extracted)
    master = pad_to_square(trimmed)
    print(f"裁剪+补正   : {trimmed.size[0]}x{trimmed.size[1]} -> {master.size[0]}x{master.size[1]}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in PNG_SIZES:
        target = OUTPUT_DIR / f"logo-bubble-{size}.png"
        resize_premultiplied(master, size).save(target, "PNG", optimize=True)
        print(f"  {target.name:<22} {size}x{size}  {target.stat().st_size / 1024:7.1f} KB")

    # favicon 由同一张 master 生成多尺寸。多带 16x16 与 48x48 而不是只放 32x32：
    # 浏览器标签页实际常用 16x16，只给 32 会让它自行降采样、反而更糊。
    ico_path = OUTPUT_DIR / "favicon.ico"
    resize_premultiplied(master, 256).save(ico_path, "ICO", sizes=ICO_SIZES)
    print(f"  {ico_path.name:<22} {'/'.join(str(s[0]) for s in ICO_SIZES):<8} "
          f"{ico_path.stat().st_size / 1024:7.1f} KB")

    print()
    print(f"全部写入：{OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
