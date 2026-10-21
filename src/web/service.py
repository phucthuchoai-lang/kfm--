import os
import re
import sys
from pathlib import Path

# 针对 Windows 控制台的 GBK 编码进行保护，避免大模型输出 Emoji 时触发 UnicodeEncodeError
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

sys.path.extend([
    str(Path(__file__).resolve().parent.parent.parent),
    str(Path(__file__).resolve().parent.parent)
])

from json_repair.json_parser import JSONParser
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_deepseek import ChatDeepSeek
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_neo4j import Neo4jGraph, Neo4jVector
from neo4j_graphrag.types import SearchType

from configuration.config import *


class ChatService:
    def __init__(self):
        self.graph = Neo4jGraph(
            url=NEO4J_CONFIG["uri"],
            username=NEO4J_CONFIG["auth"][0],
            password=NEO4J_CONFIG["auth"][1],
        )
        # 嵌入模型
        self.embedding_model = HuggingFaceEmbeddings(
            model_name='BAAI/bge-base-zh-v1.5',
            encode_kwargs={'normalize_embeddings': True},
        )
        # LLM
        self.llm = ChatDeepSeek(model='deepseek-chat', api_key=API_KEY)
        # 定义所有实体对应的混合检索 Neo4jVector 对象
        self.neo4j_vectors = {
            'Trademark': Neo4jVector.from_existing_index(
                self.embedding_model,
                url=NEO4J_CONFIG["uri"],
                username=NEO4J_CONFIG["auth"][0],
                password=NEO4J_CONFIG["auth"][1],
                index_name='trademark_vector_index',
                keyword_index_name='trademark_fulltext_index',
                search_type=SearchType.HYBRID,
            ),
            'SPU': Neo4jVector.from_existing_index(
                self.embedding_model,
                url=NEO4J_CONFIG["uri"],
                username=NEO4J_CONFIG["auth"][0],
                password=NEO4J_CONFIG["auth"][1],
                index_name='spu_vector_index',
                keyword_index_name='spu_fulltext_index',
                search_type=SearchType.HYBRID,
            ),
            'SKU': Neo4jVector.from_existing_index(
                self.embedding_model,
                url=NEO4J_CONFIG["uri"],
                username=NEO4J_CONFIG["auth"][0],
                password=NEO4J_CONFIG["auth"][1],
                index_name='sku_vector_index',
                keyword_index_name='sku_fulltext_index',
                search_type=SearchType.HYBRID,
            ),
            'Category1': Neo4jVector.from_existing_index(
                self.embedding_model,
                url=NEO4J_CONFIG["uri"],
                username=NEO4J_CONFIG["auth"][0],
                password=NEO4J_CONFIG["auth"][1],
                index_name='category1_vector_index',
                keyword_index_name='category1_fulltext_index',
                search_type=SearchType.HYBRID,
            ),
            'Category2': Neo4jVector.from_existing_index(
                self.embedding_model,
                url=NEO4J_CONFIG["uri"],
                username=NEO4J_CONFIG["auth"][0],
                password=NEO4J_CONFIG["auth"][1],
                index_name='category2_vector_index',
                keyword_index_name='category2_fulltext_index',
                search_type=SearchType.HYBRID,
            ),
            'Category3': Neo4jVector.from_existing_index(
                self.embedding_model,
                url=NEO4J_CONFIG["uri"],
                username=NEO4J_CONFIG["auth"][0],
                password=NEO4J_CONFIG["auth"][1],
                index_name='category3_vector_index',
                keyword_index_name='category3_fulltext_index',
                search_type=SearchType.HYBRID,
            )
        }
        # 定义 Parser
        self.json_parser = JsonOutputParser()
        self.str_parser = StrOutputParser()

    # 核心聊天服务流程
    def chat(self, question):
        # 兼容处理：确保传入纯字符串
        if hasattr(question, 'message'):
            question = question.message
        elif not isinstance(question, str):
            question = str(question)

        try:
            # 1. 根据用户问题，生成 Cypher 以及需要对齐的实体
            result = self._generate_cypher(question)
            cypher = result.get('cypher_query', '')
            entities_to_align = result.get('entities_to_align', [])
            print("生成的 Cypher: ", cypher)
            print("对齐之前的实体名称: ", entities_to_align)

            # 2. 实体对齐（混合检索）
            aligned_entities = self._entity_align(entities_to_align)
            print("对齐之后的实体名称: ", aligned_entities)

            # 3. 执行 Cypher 语句，得到查询结果
            query_result = self._execute_cypher(cypher, aligned_entities)
            print("查询结果: ", query_result)

            # 4. 根据用户问题和查询结果生成答案
            answer = self._generate_answer(question, query_result)
            print("最终回答: ", answer)
            return answer
        except Exception as e:
            print(f"chat 处理异常: {e}")
            # 兜底：直接让大模型回答用户，确保前端永不报错
            try:
                fallback_prompt = f"你是一个电商智能客服。用户提问：{question}。请用热情、亲切的语气简要回答用户。"
                return self.str_parser.invoke(self.llm.invoke(fallback_prompt))
            except Exception:
                return "您好！我是电商智能客服，请问有什么关于具体商品或品牌的问题需要我帮助？"

    # 1. 根据问题，调用 LLM 生成 Cypher
    def _generate_cypher(self, question):
        prompt = """
                你是一个专业的Neo4j Cypher查询生成器。你的任务是根据用户问题生成一条Cypher查询语句，用于从知识图谱中获取回答用户问题所需的信息。

                用户问题：{question}

                知识图谱结构信息：{schema_info}

                要求：
                1. 生成参数化Cypher查询语句，参数占位符必须写成 $param_0, $param_1 等形式（带有美元符号$）
                2. 识别需要对齐的实体
                3. 必须严格使用以下JSON格式输出结果
                {{
                  "cypher_query": "生成的Cypher语句",
                  "entities_to_align": [
                    {{
                      "param_name": "param_0",
                      "entity": "原始实体名称",
                      "label": "节点类型"
                    }}
                  ]
                }}"""
        prompt = PromptTemplate.from_template(prompt)
        prompt = prompt.format(question=question, schema_info=self.graph.schema)
        # 得到模型输出
        output = self.llm.invoke(prompt)
        # 解析成 JSON
        result = self.json_parser.invoke(output)
        return result

    # 2. 实体对齐（混合检索）
    def _entity_align(self, entities_to_align):
        # 常见别名映射兼容
        label_mapping = {
            'Brand': 'Trademark',
            'BaseTrademark': 'Trademark',
            'Product': 'SPU',
            'Item': 'SPU',
            'Category': 'Category3',
        }
        for index, entity_to_align in enumerate(entities_to_align):
            raw_label = entity_to_align.get('label')
            entity = entity_to_align.get('entity')
            label = label_mapping.get(raw_label, raw_label)

            # 安全检查：只有该标签已构建向量索引且 entity 非空才执行检索
            if label in self.neo4j_vectors and entity:
                try:
                    search_res = self.neo4j_vectors[label].similarity_search(entity, k=1)
                    if search_res and len(search_res) > 0:
                        entities_to_align[index]['entity'] = search_res[0].page_content
                except Exception as e:
                    print(f"实体对齐检索异常: {e}")
        return entities_to_align

    # 3. 用对齐的实体名称替换参数，执行 Cypher
    def _execute_cypher(self, cypher, aligned_entities):
        if not cypher:
            return []

        # 正则规范化：确保参数名带有 $（如 param_0 -> $param_0）
        cypher = re.sub(r'(?<!\$)\b(param_\d+)\b', r'$\1', cypher)

        params = {}
        for aligned_entity in aligned_entities:
            p_name = aligned_entity.get('param_name', '').replace('$', '')
            val = aligned_entity.get('entity', '')
            params[p_name] = val

        try:
            return self.graph.query(cypher, params=params)
        except Exception as e:
            print(f"Cypher 执行失败: {e}, Cypher: {cypher}, params: {params}")
            return []

    # 4. 生成回答
    def _generate_answer(self, question, query_result):
        prompt = """
                你是一个电商智能客服，根据用户问题，以及数据库查询结果生成一段简洁、准确、带有幽默性的自然语言回答。
                用户问题: {question}
                数据库返回结果: {query_result}
        """
        prompt = prompt.format(question=question, query_result=query_result)
        output = self.llm.invoke(prompt)
        result = self.str_parser.invoke(output)
        return result


if __name__ == '__main__':
    chat_service = ChatService()
    print(chat_service.chat("小米都有哪些产品？"))
