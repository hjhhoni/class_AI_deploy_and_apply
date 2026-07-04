import os

# 1. 明确指定走 Hugging Face 官方母站（拒绝延迟，官方有什么就能下什么）
os.environ["HF_ENDPOINT"] = "https://huggingface.co"

# 2. 强行注入你已经测试通了的本地本地代理端口
# os.environ["http_proxy"] = "http://127.0.0.1:10090"
# os.environ["https_proxy"] = "http://127.0.0.1:10090"

# 3. 忽略代理软件可能引发的 SSL 证书冲突
os.environ["HF_HUB_DISABLE_SSL_VERIFY"] = "1"

from huggingface_hub import hf_hub_download

# 配置本地保存文件夹
LOCAL_DIR = "./model/gemma-4-12b-uncensored"
os.makedirs(LOCAL_DIR, exist_ok=True)

# 官方绝对正确的开源仓库 ID
REPO_ID = "HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced"

# 对应文件清单
files_to_download = [
    "Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf",  # 主模型
    "mmproj-Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-BF16.gguf",  # 投影模型,用于多模态输入
    "mtp-gemma-4-12B-it.gguf",  # 投机解码，自带 **MTP（Multi-Token-Prediction）草稿头**做投机解码：草稿头一次预测多个 token，主模型验证，**速度提升约 60%**
]

print("🚀 正在通过代理直连 Hugging Face 官方母站拉取 12B 越狱完全体...")

for file_name in files_to_download:
    print(f"\n⚡ 正在下载: {file_name} ...")
    try:
        hf_hub_download(
            repo_id=REPO_ID,
            filename=file_name,
            local_dir=LOCAL_DIR,
            local_dir_use_symlinks=False
        )
        print(f"✅ {file_name} 下载成功！")
    except Exception as e:
        print(f"❌ 下载 {file_name} 失败，原因: {e}")

print(f"\n🎉 流程运行完毕，请检查文件夹：{LOCAL_DIR}")