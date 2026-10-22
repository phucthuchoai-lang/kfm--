# ⚡ 客服咪 · 电商智能知识图谱助手 (Smart E-Commerce Graph-RAG)

> 基于 **DeepSeek 大语言模型 + BERT 命名实体识别 + Neo4j 知识图谱** 的新一代智能电商导购问答系统。

---

## 🌟 核心特性
1. **NER 实体识别**：基于 `google-bert/bert-base-chinese` 微调的 Token Classification 实体抽取模型，精准抽离品牌、商品及核心参数。
2. **知识图谱同步**：自动将关系型业务数据库（MySQL）同步对齐至 Neo4j 图数据库，构建实体关系网络。

<p align="center">
  <img src="assets/shujuku.png" width="850" alt="知识图谱数据库" />
</p>
<p align="center">
  <img src="assets/2.png" width="850" alt="图谱实体构建" />
</p>

3. **GraphRAG 检索增强**：结合向量语义召回与 Cypher 图查询，大模型根据多跳图谱三元组进行精准结构化回答。
4. **液态玻璃前端**：
   - 晶莹纯白磨砂玻璃视觉 (`backdrop-filter: blur(32px)`)；
   - 动态交互背景画布（粒子斥力连线 + 鼠标点击冲击波涟漪）；
   - 自由活动的桌面宠物猫（支持平滑地面漫游、拉伸/压扁/融化抽象变形、连续戳猫触发「生气头变大」爆笑暴怒模式）。

<p align="center">
  <img src="assets/yanshi.png" width="850" alt="前端演示" />
</p>
<p align="center">
  <img src="assets/3.png" width="850" alt="客服咪交互" />
</p>
<p align="center">
  <img src="assets/4.png" width="850" alt="问答效果" />
</p>
<p align="center">
  <img src="assets/5.png" width="850" alt="图谱分析" />
</p>
<p align="center">
  <img src="assets/6.png" width="850" alt="多模态展示" />
</p>
<p align="center">
  <img src="assets/7.png" width="850" alt="系统架构" />
</p>

---

## 📂 项目结构
```
er_graph/
├── assets/                  # 项目演示图片与图谱截图
├── data/                    # NER 标注数据与清洗处理集
│   └── ner/
├── src/
│   ├── configuration/       # 全局配置中心 (MySQL, Neo4j, API Keys)
│   ├── datasync/            # MySQL 到 Neo4j 图谱数据同步管道
│   ├── ner/                 # BERT Token Classification 预处理、训练与推理
│   └── web/                 # FastAPI Web 服务、GraphRAG 对话逻辑与液态玻璃前端
└── .gitignore
```

---

## 🚀 快速启动

### 1. 启动 Web 对话服务
```bash
python src/web/app.py
```
服务启动后，在浏览器访问：
👉 `http://127.0.0.1:8000/static/index.html`
