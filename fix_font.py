import os
import urllib.request

# cdn 版本 (这里用 6.5.1，你可以改成自己 CSS 里对应的版本)
FA_VERSION = "6.5.1"
CDN_BASE = f"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/{FA_VERSION}/webfonts/"

# 需要的字体文件
FONTS = [
    "fa-solid-900.woff2",
    "fa-solid-900.woff",
    "fa-solid-900.ttf",
    "fa-regular-400.woff2",
    "fa-regular-400.woff",
    "fa-regular-400.ttf",
    "fa-brands-400.woff2",
    "fa-brands-400.woff",
    "fa-brands-400.ttf"
]

# 本地 webfonts 目录
LOCAL_DIR = os.path.join("static", "webfonts")
os.makedirs(LOCAL_DIR, exist_ok=True)

def download_fonts():
    for font in FONTS:
        local_path = os.path.join(LOCAL_DIR, font)
        if not os.path.exists(local_path):
            url = CDN_BASE + font
            print(f"[+] 下载 {url} -> {local_path}")
            try:
                urllib.request.urlretrieve(url, local_path)
                print("    ✅ 成功")
            except Exception as e:
                print(f"    ❌ 失败: {e}")
        else:
            print(f"[-] 已存在 {local_path}")

if __name__ == "__main__":
    download_fonts()
    print("\n完成！缺少的字体已经下载到 static/webfonts/ 里。")

