"""从源图生成 KnowRAG 的 Logo 资源（透明 PNG + favicon）。

用法：

    E:\\Agent\\develop\\miniconda3\\envs\\benzhubenzhu\\python.exe frontend/scripts/prepare_logo.py

产物（全部写入 `frontend/public/logo/`）：

    logo-512.png  512x512    PWA / 大尺寸展示
    logo-192.png  192x192    PWA
    logo-128.png  128x128    登录页
    logo-64.png    64x64     主界面侧边栏
    logo-32.png    32x32     浏览器标签页
    favicon.ico   16/32/48   浏览器标签页（多尺寸）

## 为什么抠背景不能简单地「把所有接近白色的像素变透明」

源图是**不透明**的 JPEG，圆角方形之外是白底。但这个 Logo 内部本身就有接近白色的
高光——玻璃质感的字母 K 和聊天气泡描边。如果按「接近白色就抠掉」处理，
K 和描边会被打出成片的透明破洞。

因此这里用**连通域**做法：先从图像四周边框出发做洪水填充，只把**与外部连通**的那片
白色区域变成透明；被 Logo 包住的白/浅色像素因为不与外部连通，会被完整保留。

## 为什么要预乘 alpha（premultiply）

缩小尺寸时用的是 LANCZOS，核会跨越多个像素。透明区域的 RGB 是白色，如果不做处理，
白色会被平均进边缘像素，形成一圈**苍白的光晕**（在深色背景上尤其明显）。
所以先把 RGB 乘以 alpha 再重采样，采样完再除回来。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

# --- 路径 -------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR.parent / "public" / "logo"
SOURCE = OUTPUT_DIR / "logo.jpg"

# --- 算法参数 ---------------------------------------------------------------

# 参与洪水填充的「接近白色」判定：三通道最小值 >= 该值才算背景白。
# 取 235 而不是 250，是为了容忍 JPEG 压缩在边缘产生的轻微偏色。
BACKGROUND_THRESHOLD = 235

# 羽化带的 alpha 斜坡：三通道最小值 >= FULLY_WHITE 判为全透明，
# <= OPAQUE_FLOOR 判为完全不透明，中间线性过渡。
# 这样圆角边缘的过渡像素不会被硬切成锯齿。
FULLY_WHITE = 250
OPAQUE_FLOOR = 200

# 羽化带宽度（像素）。只在「外部背景 + 这么宽的邻域」内按上式算 alpha，
# Logo 内部一律保持完全不透明——否则玻璃质感的高光会被误判成半透明。
FEATHER_RADIUS = 2

# 裁剪时的 alpha 阈值：忽略几乎全透明的残留像素，避免裁出的边界虚胖一圈。
TRIM_ALPHA_THRESHOLD = 8

PNG_SIZES = (512, 192, 128, 64, 32)
ICO_SIZES = ((16, 16), (32, 32), (48, 48))


def build_outside_mask(rgb: Image.Image, threshold: int) -> Image.Image:
    """返回 'L' 掩码：255 = 与外部连通的背景白，0 = 其余（含 Logo 内部的白）。

    从四周边框的每个白色像素做洪水填充，而不是只从四个角出发——
    只要 Logo 有一侧贴到画布边缘，只试四角就会漏掉背景。
    """
    red, green, blue = rgb.split()
    # 三通道的最小值：对「有多接近白色」最稳健的度量（避免被单一通道的偏色骗过）
    min_channel = ImageChops.darker(ImageChops.darker(red, green), blue)
    whiteish = min_channel.point(lambda value: 255 if value >= threshold else 0)

    width, height = whiteish.size
    filled = whiteish.copy()
    marker = 128

    seeds: list[tuple[int, int]] = []
    for x in range(width):
        seeds.append((x, 0))
        seeds.append((x, height - 1))
    for y in range(height):
        seeds.append((0, y))
        seeds.append((width - 1, y))

    for seed in seeds:
        # 已经被上一轮填充标记过的种子直接跳过，避免重复扫描整片区域
        if filled.getpixel(seed) == 255:
            ImageDraw.floodfill(filled, seed, marker, thresh=0)

    return filled.point(lambda value: 255 if value == marker else 0)


def remove_background(image: Image.Image) -> Image.Image:
    """把外部白色背景变成透明，返回 RGBA 图。"""
    if image.mode in ("RGBA", "LA"):
        raise SystemExit("源图已带透明通道，本脚本面向不透明白底图；请改用其它流程。")

    rgb = image.convert("RGB")
    outside = build_outside_mask(rgb, BACKGROUND_THRESHOLD)

    if outside.getbbox() is None:
        raise SystemExit(
            "没有找到与外部连通的白色背景。请确认源图是白底，"
            f"或调高 BACKGROUND_THRESHOLD（当前 {BACKGROUND_THRESHOLD}）。"
        )

    red, green, blue = rgb.split()
    min_channel = ImageChops.darker(ImageChops.darker(red, green), blue)

    span = FULLY_WHITE - OPAQUE_FLOOR

    def ramp(value: int) -> int:
        if value >= FULLY_WHITE:
            return 0
        if value <= OPAQUE_FLOOR:
            return 255
        return int((FULLY_WHITE - value) * 255 / span)

    ramp_alpha = min_channel.point(ramp)

    # 羽化带 = 外部背景向外膨胀 FEATHER_RADIUS 像素。
    # 带内按「有多白」算 alpha；带外（Logo 实体）一律 255。
    band = outside.filter(ImageFilter.MaxFilter(2 * FEATHER_RADIUS + 1))
    opaque = Image.new("L", rgb.size, 255)
    alpha = Image.composite(ramp_alpha, opaque, band)

    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def trim_to_content(image: Image.Image) -> Image.Image:
    """裁掉四周多余的全透明区域。"""
    solid = image.getchannel("A").point(lambda value: 255 if value > TRIM_ALPHA_THRESHOLD else 0)
    box = solid.getbbox()
    if box is None:
        raise SystemExit("裁剪失败：整张图都是透明的。")
    return image.crop(box)


def pad_to_square(image: Image.Image) -> Image.Image:
    """补成正方形（透明填充）。

    裁剪后的内容通常已接近正方形，但不保证；直接 resize 到方形会拉伸变形，
    所以先补边。
    """
    width, height = image.size
    side = max(width, height)
    if (width, height) == (side, side):
        return image
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - width) // 2, (side - height) // 2), image)
    return canvas


def resize_premultiplied(image: Image.Image, size: int) -> Image.Image:
    """预乘 alpha 后用 LANCZOS 缩放，避免透明区颜色混入边缘形成光晕。"""
    array = np.asarray(image, dtype=np.float32)
    alpha = array[..., 3:4] / 255.0
    array[..., :3] *= alpha  # 预乘

    premultiplied = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), "RGBA")
    resized = premultiplied.resize((size, size), Image.LANCZOS)

    out = np.asarray(resized, dtype=np.float32)
    out_alpha = out[..., 3:4]
    # 反预乘；alpha 为 0 处 RGB 无意义，除数兜底为 1 以免除零
    divisor = np.where(out_alpha > 0, out_alpha / 255.0, 1.0)
    out[..., :3] = np.clip(out[..., :3] / divisor, 0, 255)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(f"找不到源图：{SOURCE}")

    with Image.open(SOURCE) as opened:
        original_size = opened.size
        original_mode = opened.mode
        transparent = remove_background(opened)

    trimmed = trim_to_content(transparent)
    master = pad_to_square(trimmed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"源图      : {SOURCE.name}  {original_size[0]}x{original_size[1]}  mode={original_mode}")
    print(f"抠背景后  : {transparent.size[0]}x{transparent.size[1]}  （外部白底已透明）")
    print(f"裁剪内容  : {trimmed.size[0]}x{trimmed.size[1]}  （已去掉四周多余空白）")
    print(f"补正方    : {master.size[0]}x{master.size[1]}")
    print()

    for size in PNG_SIZES:
        target = OUTPUT_DIR / f"logo-{size}.png"
        resize_premultiplied(master, size).save(target, "PNG", optimize=True)
        print(f"  {target.name:<16} {size}x{size}  {target.stat().st_size / 1024:7.1f} KB")

    # favicon 由同一张 master 生成多尺寸。多带 16x16 与 48x48 而不是只放 32x32：
    # 浏览器标签页实际常用 16x16，只给 32 会让它自行降采样，反而更糊。
    ico_path = OUTPUT_DIR / "favicon.ico"
    resize_premultiplied(master, 256).save(ico_path, "ICO", sizes=ICO_SIZES)
    print(f"  {ico_path.name:<16} {'/'.join(str(s[0]) for s in ICO_SIZES):<8} "
          f"{ico_path.stat().st_size / 1024:7.1f} KB")

    print()
    print(f"全部写入：{OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
