# 自定义预测器
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from src.configuration.config import *

class Predictor:
    # 初始化
    def __init__(self, model, tokenizer, device):
        self.model = model.to(device)
        self.model.eval()
        self.tokenizer = tokenizer
        self.device = device

    # 预测方法（输出每个字的 BIO 标签）
    def predict(self, inputs: str | list[str]):
        is_str = isinstance(inputs, str)
        if is_str:
            inputs = [inputs]
        # 1. 预分词，得到字符列表
        tokens_list = [list(item) for item in inputs]
        # 2. 用分词器id化处理
        inputs_tensor = self.tokenizer(
            tokens_list,
            is_split_into_words=True,
            padding=True,
            truncation=True,
            return_tensors='pt'
        )
        # 3. 加载到设备
        inputs_tensor = {k: v.to(self.device) for k, v in inputs_tensor.items()}
        # 4. 前向传播，推理预测
        with torch.no_grad():
            outputs = self.model(**inputs_tensor)
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=-1).tolist()

        # 5. 将id列表转化为 BIO 标签
        final_predictions = []
        for tokens, prediction in zip(tokens_list, predictions):
            # 截取预测输出中，去掉开头的 [CLS]
            prediction = prediction[1: len(tokens) + 1]
            # 转换成标签字符串
            final_prediction = [self.model.config.id2label[id] for id in prediction]
            final_predictions.append(final_prediction)

        if is_str:
            return final_predictions[0]
        return final_predictions

    # 抽取实体方法（缩进 4 格，与 predict 平级）
    def extract(self, inputs: str | list[str]):
        is_str = isinstance(inputs, str)
        if is_str:
            inputs = [inputs]
        # 得到预测标签列表
        predictions = self.predict(inputs)
        # 从当前列表中，抽取实体列表
        entities_list = []
        for text_item, labels in zip(inputs, predictions):
            # 调用内部函数，抽取一个数据样本的所有实体标签
            entities = self._extract_entities(list(text_item), labels)
            entities_list.append(entities)
        if is_str:
            return entities_list[0]
        return entities_list

    # 内部方法：根据连续的 B-I-I... 拼接实体
    def _extract_entities(self, tokens, labels):
        entities = []
        current_entity = ""
        for token, label in zip(tokens, labels):
            # 如果标签是B，开始保存新实体
            if label == 'B':
                if current_entity:
                    entities.append(current_entity)
                current_entity = token
            # 如果标签是I，继续追加实体内容
            elif label == 'I':
                if current_entity:
                    current_entity += token
            # 如果标签是O，就将实体抽取出来（如果存在），添加到列表
            else:
                if current_entity:
                    entities.append(current_entity)
                current_entity = ""

        if current_entity:
            entities.append(current_entity)

        return entities


def predict():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = AutoModelForTokenClassification.from_pretrained(str(CHECKPOINT_DIR / NER_DIR / 'best_model'))
    tokenizer = AutoTokenizer.from_pretrained(str(CHECKPOINT_DIR / NER_DIR / 'best_model'))
    
    # 定义预测器
    predictor = Predictor(model, tokenizer, device)
    
    # 测试数据
    text = [
        '麦德龙德国进口双心多维叶黄素护眼营养软胶囊30粒x3盒眼干涩',
        '热风2018年秋季时尚女士运动风休闲鞋深口系带单鞋h11w8103'
    ]

    # 抽取实体
    entities = predictor.extract(text)
    print("实体抽取结果：")
    print(entities)


if __name__ == '__main__':
    predict()
