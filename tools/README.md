# Tools

## remove_sobrief_watermark.py — Xóa watermark "SoBrief.com" khỏi ảnh bìa sách

Ảnh bìa trong [../books/](../books/) bị dính watermark chữ **"SoBrief.com"** bán trong
suốt ở góc **trên bên phải**. Tool này xóa nó đi.

### Cách hoạt động

Watermark nằm **cố định một vị trí** trên mọi ảnh (góc trên-phải), là chữ bán trong
suốt đổi màu theo nền (xám trên nền sáng, trắng trên nền tối). Vì vậy tool:

1. **Dựng mask theo đúng hình chữ.** Trung bình bản đồ cạnh (Sobel) qua hàng trăm ảnh
   → chữ luôn cùng vị trí nên hiện thành "bóng ma" rõ nét → threshold + morphology ra
   được mask đúng hình các chữ cái. Mask lưu sẵn ở [sobrief_mask.png](sobrief_mask.png).
2. **Chỉ inpaint đúng nét chữ** (OpenCV `INPAINT_TELEA`), không đụng vùng nền xung
   quanh → sạch hơn nhiều so với bôi đen cả góc, giữ được hoạ tiết/chi tiết bìa.

Vùng watermark (hệ toạ độ ảnh 480px ngang): `x 330–478, y 8–42`, neo theo góc trên-phải
nên áp dụng được cho cả ảnh `480×720` lẫn `480×715`.

### Chỉ ảnh 480px ngang mới có watermark

2349/2353 ảnh là khổ 480px ngang và có watermark. 4 ảnh nhỏ hơn đến từ nguồn khác,
**không có** watermark → tool tự động bỏ qua và liệt kê ra:

- `deep-mentoring.webp`
- `from-triggered-to-tranquil.webp`
- `the-psychology-of-the-simpsons.webp`
- `trauma-and-the-soul.webp`

### Yêu cầu

```bash
pip install numpy opencv-python-headless
```

### Cách dùng

```bash
# Xem thử trước/sau vài ảnh (ghi 1 file PNG so sánh, KHÔNG đổi gì trong books/)
python tools/remove_sobrief_watermark.py --preview 8

# Chạy thử: báo cáo sẽ đổi những gì, không ghi file
python tools/remove_sobrief_watermark.py --dry-run

# Xóa watermark, ghi đè tại chỗ (books/ đang được git theo dõi nên revert dễ)
python tools/remove_sobrief_watermark.py --in-place

# Hoặc ghi bản đã xóa ra thư mục khác, giữ nguyên ảnh gốc
python tools/remove_sobrief_watermark.py --out books_clean

# Dựng lại mask từ bộ ảnh (chỉ cần khi watermark thay đổi)
python tools/remove_sobrief_watermark.py --build-mask
```

Tuỳ chọn khác: `--dir` (thư mục ảnh, mặc định `books`), `--glob` (mẫu tên file, mặc
định `*.webp`), `--quality` (chất lượng webp, mặc định 95), `--workers` (số luồng
song song).

### Hoàn tác

Vì `--in-place` ghi đè file gốc, hãy revert qua git nếu cần:

```bash
git checkout books/        # trả lại toàn bộ ảnh gốc (có watermark)
git status --porcelain books/ | wc -l   # đếm số file đang bị sửa
```

### Lưu ý

- Ảnh nền **rất nhiều chi tiết** (vd `a-billion-wicked-thoughts.webp`) có thể còn một
  vệt hơi mềm chỗ chữ cũ — chữ vẫn mất hẳn, chỉ là nền tái tạo không hoàn hảo 100%.
- File hỗ trợ **tên file Unicode** (đọc/ghi qua `np.fromfile` + `cv2.imdecode/imencode`).
