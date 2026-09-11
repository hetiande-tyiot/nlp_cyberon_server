"""
MacBERT 分层分类推理 Pipeline

层次:
  文本 → 主类别模型 → 子类别模型 → 最终结果

特殊处理:
  - 檢舉投訴: 只有 1 个子类 (爆竹煙火)，直接映射，不加载模型
  - 災害: 若子类模型不存在，sub_category 返回 None

用法示例:
  from inference_pipeline import HierarchicalClassifier

  clf = HierarchicalClassifier()
  result = clf.predict("一一九，你好，我家附近有火災，請快來。")
  print(result)
  # {'main_category': '火警', 'main_conf': 0.987,
  #  'sub_category': '集合住宅',  'sub_conf': 0.923,
  #  'category': '火警-集合住宅',  'stt_text': '...'}

  # 批量推理
  results = clf.predict_batch(["急病求救", "電梯卡住了"])
"""

import json
import os
from typing import Optional

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# ─── 特殊规则 ─────────────────────────────────────────────────────────────────

# 只有 1 个子类、无需模型的主类别 → 直接映射到唯一子类
FIXED_SUB_CATEGORY: dict[str, str] = {
    "檢舉投訴": "爆竹煙火",
}

# 子类模型数据不足、默认不训练的主类别 (若有模型文件则仍会使用)
LOW_DATA_MAIN: set[str] = {"災害"}

# ─── 核心类 ───────────────────────────────────────────────────────────────────

class HierarchicalClassifier:
    """
    两阶段分层分类器。
    模型按需懒加载，避免显存浪费。
    """

    def __init__(
        self,
        models_base: str = "/root/autodl-tmp/models/",
        device: Optional[str] = None,
        max_len: int = 128,
    ):
        self.models_base = models_base
        self.max_len     = max_len
        self.device      = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # 懒加载缓存
        self._tokenizers: dict[str, AutoTokenizer]                          = {}
        self._models:     dict[str, AutoModelForSequenceClassification]     = {}
        self._id2label:   dict[str, dict[int, str]]                         = {}

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    def _model_dir(self, key: str) -> str:
        """key = 'main' 或 主类别名称（用于子模型）"""
        if key == "main":
            return os.path.join(self.models_base, "TW-119-BERT_main")
        return os.path.join(self.models_base, f"TW-119-BERT-sub_{key}")

    def _load(self, key: str) -> bool:
        """加载模型到缓存，返回是否成功。"""
        if key in self._models:
            return True

        model_dir = self._model_dir(key)
        if not os.path.isdir(model_dir):
            return False

        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        model.eval()
        model.to(self.device)

        label_map_path = os.path.join(model_dir, "label_map.json")
        with open(label_map_path, encoding="utf-8") as f:
            data = json.load(f)
        # JSON 键为字符串，需转为 int
        id2label = {int(k): v for k, v in data["id2label"].items()}

        self._tokenizers[key] = tokenizer
        self._models[key]     = model
        self._id2label[key]   = id2label
        return True

    def _infer(self, key: str, text: str) -> tuple[str, float]:
        """对单条文本做推理，返回 (predicted_label, confidence)。"""
        tokenizer = self._tokenizers[key]
        model     = self._models[key]
        id2label  = self._id2label[key]

        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_len,
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = model(**inputs).logits

        probs   = torch.softmax(logits, dim=-1).cpu().numpy()[0]
        pred_id = int(np.argmax(probs))
        return id2label[pred_id], float(probs[pred_id])

    def _infer_batch(self, key: str, texts: list[str]) -> list[tuple[str, float]]:
        """对多条文本做批量推理，返回 [(label, conf), ...]。"""
        tokenizer = self._tokenizers[key]
        model     = self._models[key]
        id2label  = self._id2label[key]

        inputs = tokenizer(
            texts,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_len,
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = model(**inputs).logits

        probs   = torch.softmax(logits, dim=-1).cpu().numpy()
        pred_ids = np.argmax(probs, axis=-1)
        return [(id2label[pid], float(probs[i][pid])) for i, pid in enumerate(pred_ids)]

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def predict(self, text: str) -> dict:
        """
        对单条文本做层次分类。

        返回:
        {
            "stt_text":      原始文本,
            "main_category": 主类别,
            "main_conf":     主类置信度 (0~1),
            "sub_category":  子类别 (若不可用则为 None),
            "sub_conf":      子类置信度 (若不可用则为 None),
            "category":      "{main}-{sub}" 或 "{main}" (若 sub 为 None),
        }
        """
        # Step 1: 主类别
        if not self._load("main"):
            raise RuntimeError(
                f"主类别模型不存在: {self._model_dir('main')}\n"
                "请先运行: python train_hierarchical.py --task main"
            )
        main_cat, main_conf = self._infer("main", text)

        # Step 2: 子类别
        if main_cat in FIXED_SUB_CATEGORY:
            sub_cat  = FIXED_SUB_CATEGORY[main_cat]
            sub_conf = 1.0
        elif self._load(main_cat):
            sub_cat, sub_conf = self._infer(main_cat, text)
        else:
            sub_cat  = None
            sub_conf = None

        category = f"{main_cat}-{sub_cat}" if sub_cat else main_cat

        return {
            "stt_text":      text,
            "main_category": main_cat,
            "main_conf":     round(main_conf, 6),
            "sub_category":  sub_cat,
            "sub_conf":      round(sub_conf, 6) if sub_conf is not None else None,
            "category":      category,
        }

    def predict_batch(self, texts: list[str]) -> list[dict]:
        """
        对多条文本批量推理（主类别阶段全量批次，子类别阶段按主类分组批次）。
        """
        if not texts:
            return []

        # Step 1: 主类别批量推理
        if not self._load("main"):
            raise RuntimeError(
                f"主类别模型不存在: {self._model_dir('main')}\n"
                "请先运行: python train_hierarchical.py --task main"
            )
        main_results = self._infer_batch("main", texts)

        # Step 2: 按主类别分组，批量推理子类别
        # 先收集每个主类别需要推理的 (原始index, text) 列表
        groups: dict[str, list[tuple[int, str]]] = {}
        for i, (main_cat, _) in enumerate(main_results):
            if main_cat not in FIXED_SUB_CATEGORY:
                groups.setdefault(main_cat, []).append((i, texts[i]))

        # 每组加载子模型并批量推理
        sub_results: dict[int, tuple[Optional[str], Optional[float]]] = {}

        for main_cat, idx_text_pairs in groups.items():
            indices = [p[0] for p in idx_text_pairs]
            group_texts = [p[1] for p in idx_text_pairs]

            if self._load(main_cat):
                preds = self._infer_batch(main_cat, group_texts)
                for idx, (sub_cat, sub_conf) in zip(indices, preds):
                    sub_results[idx] = (sub_cat, sub_conf)
            else:
                for idx in indices:
                    sub_results[idx] = (None, None)

        # Step 3: 组装最终结果
        output = []
        for i, text in enumerate(texts):
            main_cat, main_conf = main_results[i]

            if main_cat in FIXED_SUB_CATEGORY:
                sub_cat  = FIXED_SUB_CATEGORY[main_cat]
                sub_conf = 1.0
            else:
                sub_cat, sub_conf = sub_results.get(i, (None, None))

            category = f"{main_cat}-{sub_cat}" if sub_cat else main_cat

            output.append({
                "stt_text":      text,
                "main_category": main_cat,
                "main_conf":     round(main_conf, 6),
                "sub_category":  sub_cat,
                "sub_conf":      round(sub_conf, 6) if sub_conf is not None else None,
                "category":      category,
            })

        return output

    def warmup(self):
        """预加载所有可用模型到 GPU，避免首次推理延迟。"""
        for key in ["main"] + list(FIXED_SUB_CATEGORY.keys()):
            if key == "main" or key in FIXED_SUB_CATEGORY:
                pass  # FIXED_SUB 不需要模型
        self._load("main")

        # 加载所有存在的子模型
        main_cats = list(self._id2label.get("main", {}).values())
        for cat in main_cats:
            if cat not in FIXED_SUB_CATEGORY:
                self._load(cat)

    def list_loaded_models(self) -> list[str]:
        return list(self._models.keys())


# ─── CLI 入口 ─────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="MacBERT 分层分类推理")
    parser.add_argument(
        "--text", type=str, default=None,
        help="单条文本推理（与 --input_file 二选一）",
    )
    parser.add_argument(
        "--input_file", type=str, default=None,
        help="输入 JSON 文件（列表或每行一个 stt_text 字段的对象）",
    )
    parser.add_argument(
        "--output_file", type=str, default=None,
        help="推理结果输出路径（默认打印到 stdout）",
    )
    parser.add_argument(
        "--models_base", type=str, default="/root/autodl-tmp/models/",
    )
    parser.add_argument("--batch_size", type=int, default=32)
    args = parser.parse_args()

    clf = HierarchicalClassifier(models_base=args.models_base)

    if args.text:
        result = clf.predict(args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.input_file:
        with open(args.input_file, encoding="utf-8") as f:
            data = json.load(f)

        # 支持 list[str] 或 list[{stt_text: ...}]
        if data and isinstance(data[0], str):
            texts = data
        else:
            texts = [r["stt_text"] for r in data]

        # 分批推理
        all_results = []
        for i in range(0, len(texts), args.batch_size):
            batch = texts[i : i + args.batch_size]
            all_results.extend(clf.predict_batch(batch))
            if (i // args.batch_size + 1) % 10 == 0:
                print(f"已处理 {i + len(batch)}/{len(texts)} 条")

        if args.output_file:
            with open(args.output_file, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
            print(f"结果已保存至 {args.output_file}")
        else:
            print(json.dumps(all_results, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
