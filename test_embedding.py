from services.embedding import EmbeddingClient

def main() -> None:
    client = EmbeddingClient()
    text = "测试 embedding 是否正常工作"
    print("准备发送到服务的文本：", text)
    vec = client.embed(text)
    print("返回向量长度:", len(vec))
    # 安全起见，不打印完整向量，只看前几个值
    print("向量前 5 个值:", vec[:5])

if __name__ == "__main__":
    main()