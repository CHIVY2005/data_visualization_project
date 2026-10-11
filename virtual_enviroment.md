# 📦 Hướng dẫn môi trường & Git

---

## 🐍 1. Tạo và sử dụng Virtual Environment

### Tạo môi trường ảo
```bash
python -3.13 -m venv .venv
```
hoặc
```bash
py -3.13 -m venv .venv
```

### Kích hoạt môi trường (Windows)
```bash
.\.venv\Scripts\activate
```

### Sau khi kích hoạt

Từ:

PS C:\WINDOWS\System32>

Sang:

(.venv) PS F:\Personal Projects\qưert>


### Di chuyển thu mục trong PowerShell
```bash
cd "F:\Personal Projects\qưert"
```

## 📥 2. Cài đặt / Gỡ thư viện

### Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### Gỡ toàn bộ dependencies
```bash
pip uninstall -r requirements.txt
```

## 🌿 3. Git Workflow

### Clone project lần đầu
```bash
git clone https://github.com/Duy-DS/Atlas_Agent.git
```

### Pull code (những lần sau)
```bash
cd "F:\Study Materials\Môn Ngành\Big Data\BigData_PJ_v2\stock_portfolio-bigdata_pj"
git pull
```

### Push code lên nhánh
```bash
git push -u origin "branch_name"
```

### Kiểm tra danh sách nhánh
```bash
git branch
```

### Tạo nhánh mới
```bash
git checkout -b ten-nhanh-cua-ban
```



### Chuyển nhánh
```bash
git checkout ten-nhanh-cua-ban
```

### Gộp nhánh
#### Bước 1: Cập nhật danh sách nhánh mới nhất từ GitHub
```bash
git fetch origin
```

#### Bước 2: Chuyển về nhánh của bạn và đảm bảo code đang "sạch"
```bash
# 1. Chuyển sang nhánh branch_of_Duy
git checkout branch_of_Duy

# 2. Kiểm tra trạng thái
git status
```

#### Bước 3: Tiến hành gộp code từ nhánh khác vào

Nếu muốn lấy code mới nhất từ nhánh main trên GitHub về:

```bash
git merge origin/main
```

Nếu muốn lấy code từ một nhánh khác chạy dưới máy local (ví dụ tên nhánh đó là feature_abc):

```bash
git merge feature_abc
```

## ▶️ 4. Chạy chương trình

```bash
python src/discord_overall_nofi.py
```

## 🔙 5. Di chuyển thư mục

Đang ở:
F:\Study Materials\Môn Ngành\Big Data\BigData_PJ_v2\stock_portfolio-bigdata_pj\src>

Muốn quay lại thư mục trước:
cd ..