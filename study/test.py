import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_ollama import OllamaLLM

model = OllamaLLM(model="qwen3:8b")

# 原先写成 input("你是什么模型")：那是等键盘输入，不是把这句话发给模型
res = model.invoke(input="你能做什么")
print(res)
