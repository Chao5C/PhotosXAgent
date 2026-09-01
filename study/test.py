from sys import prefix

from langchain_ollama import OllamaLLM
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
model = OllamaLLM(model="qwen3:4b")
#示例模板
example_template = PromptTemplate.from_template("单词：{word}，反义词：{antonym}")
#数据注入
example_data = [
    {"word":"da", "antonym":"xiao"},
    {"word": "shang", "antonym": "xia"}
]
fewshottemplate = FewShotPromptTemplate(
    example_prompt=example_template,#
    examples=example_data,
    prefix = "告诉我所给单词的反义词，下面是示例",              #示例之前提示词
    suffix = "基于前面的示例告诉我，{input_word}的反义词",              #后提示词
    input_variables=["input_word"]      #声明在前缀或后缀中要注入的变量名
)
promopt_text = fewshottemplate.invoke(input={"input_word":"zuo"}).to_string()
print(promopt_text)
res1 = model.stream(input = promopt_text)
for chunks in res1:
    print(chunks,end="",flush=True)
# 原先写成 input("你是什么模型")：那是等键盘输入，不是把这句话发给模型
res = model.stream(input="")
for chunk in res:
    print(chunk,end="",flush=True)

