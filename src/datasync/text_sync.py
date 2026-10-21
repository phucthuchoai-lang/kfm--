import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification

from configuration.config import *
from utils import MysqlReader, Neo4jWriter
from ner.predict import Predictor

class TextSynchronizer():
    def __init__(self):
        self.reader = MysqlReader()
        self.writer = Neo4jWriter()
        # 定义一个实体的提取器，本质就是Predictor
        self.extractor = self._init_extractor()

    # 内部函数：初始化一个Predictor
    def _init_extractor(self):
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model = AutoModelForTokenClassification.from_pretrained(str(CHECKPOINT_DIR / NER_DIR / 'best_model'))
        tokenizer = AutoTokenizer.from_pretrained(str(CHECKPOINT_DIR / NER_DIR / 'best_model'))

        return Predictor(model, tokenizer, device)

    # 同步Tag标签
    def sync_tag(self):
        # 1. 从MySQL提取商品描述信息
        sql = """
            select id, description
            from spu_info
        """
        spu_desc = self.reader.read(sql)
        # 2. 拆分spu id 和 desc
        ids = [ item['id'] for item in spu_desc ]
        descs = [ item['description'] for item in spu_desc ]

        # 3. 提取所有数据的 Tag 列表
        tags_list = self.extractor.extract(descs)

        # for id, tags in zip(ids, tags_list):
        #     print(id, tags)

        # 4. 构建Tag节点的属性（id,name），以及 SPU → Tag 关系（start_id，end_id）
        tag_properties = []
        relations = []

        for id, tags in zip(ids, tags_list):
            # 遍历当前SPU的每个标签
            for index, tag in enumerate(tags):
                # 构建Tag属性
                tag_id = '-'.join([str(id), str(index)])
                property = {'id': tag_id, 'name': tag}
                tag_properties.append(property)
                # 构建关系
                relation = {'start_id': id, 'end_id': tag_id }
                relations.append(relation)

        # 5. 写入Neo4j
        self.writer.write_nodes( "Tag", tag_properties)
        self.writer.write_relations("Have", "SPU", "Tag", relations)


if __name__ == '__main__':

    synchronizer = TextSynchronizer()

    synchronizer.sync_tag()