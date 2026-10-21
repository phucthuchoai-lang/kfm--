import os
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

import evaluate
from datasets import load_from_disk
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    TrainingArguments,
    Trainer,
    DataCollatorForTokenClassification,
    EvalPrediction
)

from src.configuration.config import *

# 1. 分词器
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

# 标签映射
id2label = {idx: label for idx, label in enumerate(LABELS)}
label2id = {label: idx for idx, label in enumerate(LABELS)}

# 2. 模型
model = AutoModelForTokenClassification.from_pretrained(
    MODEL_NAME,
    num_labels=len(LABELS),
    id2label=id2label,
    label2id=label2id,
)

# 3. 加载数据集
train_dataset = load_from_disk(str(PROCESSED_DATA_DIR / 'train'))
valid_dataset = load_from_disk(str(PROCESSED_DATA_DIR / 'valid'))

# 4. 数据整理器
data_collator = DataCollatorForTokenClassification(
    tokenizer=tokenizer,
    padding=True,
    return_tensors="pt"
)

# 5. 训练参数
args = TrainingArguments(
    output_dir=str(CHECKPOINT_DIR / NER_DIR),

    report_to="tensorboard",                     # 👈 显式开启 TensorBoard 记录


    num_train_epochs=EPOCHS,                     # 训练总轮次
    per_device_train_batch_size=BATCH_SIZE,      # batch 大小
    learning_rate=LEARNING_RATE,                 # 学习率

    save_strategy="steps",                       # 保存策略
    save_steps=SAVE_STEPS,                       # 每20次迭代进行一次保存
    save_total_limit=3,                          # 最多保存3个检查点

    fp16=True,                                   # 开启混合精度训练

    logging_strategy='steps',                    # 日志写入策略
    logging_steps=SAVE_STEPS,

    eval_strategy='steps',                       # 评估策略
    eval_steps=SAVE_STEPS,

    metric_for_best_model='eval_overall_recall',          # 模型评估指标
    greater_is_better=True,
    load_best_model_at_end=True                  # 训练结束加载最佳模型
)

# 6. 评估指标函数
seqeval = evaluate.load('seqeval')

def compute_metrics(prediction: EvalPrediction):
    logits = prediction.predictions
    preds = logits.argmax(axis=-1)
    labels = prediction.label_ids

    # 过滤掉 -100 并将 id 转换为 BIO 标签
    true_predictions = [
        [id2label[p] for (p, l) in zip(pred, label) if l != -100]
        for pred, label in zip(preds, labels)
    ]
    true_labels = [
        [id2label[l] for (p, l) in zip(pred, label) if l != -100]
        for pred, label in zip(preds, labels)
    ]

    return seqeval.compute(predictions=true_predictions, references=true_labels)

#7.早停回调

early_stopping_callback = EarlyStoppingCallback(early_stopping_patience=2)

#  创建训练器
trainer = Trainer(
    model=model,
    train_dataset=train_dataset,
    eval_dataset=valid_dataset,
    args=args,
    data_collator=data_collator,
    compute_metrics=compute_metrics,
    callbacks=[early_stopping_callback]
)

# 8. 训练
trainer.train()

# 9. 模型保存
trainer.save_model(str(CHECKPOINT_DIR / NER_DIR / 'best_model'))
