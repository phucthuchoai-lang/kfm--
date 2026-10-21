# import sys
# from pathlib import Path
# sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
#
# import os
# os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from dotenv import load_dotenv
load_dotenv()

from datasets import load_dataset
from transformers import AutoTokenizer



from src.configuration.config import RAW_DATA_FILE, MODEL_NAME, PROCESSED_DATA_DIR, LABELS


def process():
    # 加载数据
    # 1.读取数据
    dataset = load_dataset("json", data_files=RAW_DATA_FILE )['train']

    # 2.去除多余列
    dataset = dataset.remove_columns(["id", "annotator", "annotation_id", "created_at", "updated_at", "lead_time"])

    # 3.划分数据集
    dataset_dict = dataset.train_test_split(train_size=0.8)
    dataset_dict['test'], dataset_dict['valid'] = dataset_dict['test'].train_test_split(test_size=0.5).values()

    # 4.定义分词器
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    # 5.数据编码（输入文本和标签）
    def encode(example):
        # 5.1:将文本数据转成字符列表
        tokens = list(example['text'])
        # 5.2 文本编码
        inputs = tokenizer(tokens, truncation=True, is_split_into_words=True)
        # 5.3 进行实体标注
        entities = example['label']
        # 定义标注列表，存放id，默认都为‘O’的id
        labels = [ LABELS.index('O') ] * len(tokens)
        # 遍历每个Tag，标记为'B'和'I'的id
        for entity in entities:
            start = entity['start']
            end = entity['end']
            labels[start:end] = [LABELS.index('B')] + [LABELS.index('I')] * (end - start - 1)
        #前后加上id = -100，对应CLS和SEP
        labels = [-100] + labels +[-100]
        inputs['labels'] = labels
        return inputs

    dataset_dict = dataset_dict.map( encode,remove_columns=['text','label'])
    print(dataset_dict['train'][0])

    # 6.保存到文件
    dataset_dict.save_to_disk(PROCESSED_DATA_DIR)




if __name__ == '__main__':
    process()