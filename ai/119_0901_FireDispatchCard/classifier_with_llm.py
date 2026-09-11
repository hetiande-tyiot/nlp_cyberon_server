"""
classifier_with_llm.py
━━━━━━━━━━━━━━━━━━━━━━
MacBERT 分层分类 + LLM 复核 纯函数库

适用模型:
  - 分类器: /root/autodl-tmp/models/TW-119-BERT-sub_救護/
             /root/autodl-tmp/models/TW-119-BERT-sub_火警_v2/
  - LLM:    /root/autodl-tmp/models/TW-119-Model/TW-119-Model.gguf

触发逻辑:
  若分类器的预测标签属于「高频误判标签集合」，则将文本送入 LLM 进行语义复核；
  最终以 LLM 的判断为准。

对外接口:
  SubCategoryClassifier   — 单个子类分类器（含 LLM 复核）
  predict_119             — 便捷函数，一次性对文本完成分类+复核
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# ─────────────────────────────────────────────────────────────────────────────
# 常量：高频误判对 & 触发标签
# 数据来源: export_misclassified.py 生成的 error_distribution
# ─────────────────────────────────────────────────────────────────────────────

# (真实标签 → 预测标签) 高频误判对（误判数量超过阈值的对）
# 用于文档说明；实际触发逻辑使用下方派生的 _LLM_TRIGGER_LABELS
_CONFUSION_PAIRS: dict[str, list[tuple[str, str]]] = {
    "救護": [
        ("急病",   "一般受傷"), ("急病",   "路倒"),    ("一般受傷", "急病"),
        ("急病",   "其它"),   ("一般受傷", "路倒"),    ("急病",   "車禍"),
        ("車禍",   "路倒"),   ("一般受傷", "車禍"),    ("急病",   "精神異常"),
        ("路倒",   "一般受傷"), ("車禍",   "一般受傷"), ("車禍",   "急病"),
        ("路倒",   "急病"),   ("路倒",   "車禍"),    ("精神異常", "急病"),
        ("其它",   "急病"),   ("一般受傷", "打架受傷"),
    ],
    "火警": [
        ("集合住宅", "查看案件"), ("查看案件", "集合住宅"),
        ("查看案件", "警報器作響"), ("查看案件", "電線桿(電纜)"),
        ("警報器作響", "查看案件"), ("集合住宅", "警報器作響"),
        ("警報器作響", "集合住宅"), ("集合住宅", "電線桿(電纜)"),
        ("電線桿(電纜)", "查看案件"),
    ],
}

# 对于每个主类别，当分类器的预测标签在此集合中时，触发 LLM 复核
_LLM_TRIGGER_LABELS: dict[str, set[str]] = {
    main_cat: {pair[1] for pair in pairs}
    for main_cat, pairs in _CONFUSION_PAIRS.items()
}

# ─────────────────────────────────────────────────────────────────────────────
# LLM Prompt 配置：各子类的标签描述（繁体中文，与报案语境一致）
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# 分类提示词：针对高噪音 STT 文本，改用关键词优先级规则而非语义描述
# 文本特点：语音转文字、重复词多、台湾口语腔调、报案人与接线员对话交织
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "你是119報案電話分類專家。"
    "文字為語音辨識轉寫，含噪音與重複詞，請聚焦關鍵詞與核心語義。"
    "只輸出類別名稱，禁止輸出任何其他文字。"
)

# 关键词规则型提示词（按优先级排列，越靠前优先级越高）
_RULE_PROMPTS: dict[str, str] = {

    "火警": """\
【報案原文】
{text}

【分類器預測（供參考）】
{top3_block}

【各類別判斷特徵】
關鍵詞是「線索」而非「充分條件」，需結合整體語義判斷事故的真正主體。

▸ 電線桿(電纜)
  主體是電線桿/電纜/電箱/變壓器本身起火冒煙
  常見詞：電線桿、電纜、電箱、變電箱、走火、電線起火、變壓器
  ✗ 排除：只是提到電線桿是地點（如「電線桿旁的大樓失火」→選集合住宅）

▸ 警報器作響
  火警偵測系統自動觸發，現場未目擊明火，多為疑似誤報
  常見詞：警報器、偵測器、自動警報設備、一直叫/響
  ✗ 排除：警報響起後確認有實際火災（→改選集合住宅）

▸ 集合住宅
  住宅建築（公寓/大樓/透天厝）有實際火災，目擊明火或大量濃煙，情況緊急
  常見詞：失火、著火、起火、冒煙，且提及樓層/大樓/住家
  ✗ 排除：只聞到異味但未目擊明火或大量煙霧

▸ 查看案件
  情況不明，派員到場確認，報案人不確定是否為真實火災
  常見情境：聞到燒焦味/瓦斯味但找不到火源、輕微煙霧原因不明、鄰居反映異味
  ✗ 排除：已有明確起火跡象（有火焰/大量濃煙）

⚠️ 易混淆提示：
  集合住宅 vs 查看案件 → 有無目擊明火或大量濃煙是關鍵，「有煙有火」→集合住宅，「聞到味道不確定」→查看案件
  集合住宅 vs 警報器作響 → 警報響後有找到真實火源 → 集合住宅

請直接回答類別名稱，禁止輸出其他任何內容。""",

    "救護": """\
【報案原文】
{text}

【分類器預測（供參考）】
{top3_block}

【各類別判斷特徵】
關鍵詞是「線索」而非「充分條件」，需結合整體語義判斷事故的真正主體。

▸ 割腕
  傷者以利器自傷手腕，為自殺/自傷行為
  常見詞：割腕、割自己、自傷、用刀割手腕

▸ 吞食藥物
  誤食或故意服用過量藥物/毒物/化學品
  常見詞：吃藥、服毒、誤食藥、吞藥、藥物過量、喝農藥

▸ 車禍
  交通事故造成傷亡，事故主體是車輛碰撞
  常見詞：車禍、被車撞、機車、撞車、追撞、肇事、騎車摔車
  ✗ 排除：只是描述發生地點在路上（如「路上有人昏倒」→看其他特徵）

▸ 打架受傷
  人際暴力衝突導致受傷，有施暴者存在
  常見詞：打架、被打、互毆、持刀、砍傷、攻擊
  ✗ 排除：傷者是自傷（→割腕）

▸ 精神異常
  精神疾病發作或嚴重情緒失控，非一般急病
  常見詞：精神疾病、精神障礙、發作、攻擊傾向、亂叫亂跑、行為怪異
  ✗ 排除：只是情緒激動但有明確身體急症（→急病）

▸ 路倒
  路邊/公共場所發現「不認識的陌生人」倒臥，報案人是路過發現者
  特徵：「有個人倒在...」「不知道是誰」，報案人與傷者互不認識
  ✗ 排除：報案人認識傷者（家人/朋友在路上倒下→急病或一般受傷）

▸ 一般受傷
  有明確外力造成傷口（跌倒/碰撞/撞傷/割傷），傷者身份已知，非車禍或打架
  常見情境：在家跌倒、被東西砸到、意外割傷

▸ 急病
  熟識的人（家人/朋友/自己）突發身體不適：心臟、中風、昏倒、呼吸困難，無外力因素
  常見詞：不舒服、昏倒、喘不過氣、心臟病、中風

▸ 其它
  明確不屬於以上任何類別（如轉接案件、確認家屬過世、工地等特殊情況）
  若有任何類別部分符合，優先選那個類別

⚠️ 易混淆提示：
  路倒 vs 急病 → 是否認識傷者：陌生人→路倒，家人/朋友/自己→急病
  一般受傷 vs 急病 → 有無外力碰撞：跌倒/撞到→一般受傷，自發身體不適→急病
  精神異常 vs 其它 → 有行為失控/精神病史→精神異常，其餘特殊情況→其它

請直接回答類別名稱，禁止輸出其他任何內容。""",
}

# ─────────────────────────────────────────────────────────────────────────────
# 推理结果数据类
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PredictionResult:
    stt_text:        str
    main_category:   str
    final_label:     str                   # 最终采用的子类标签
    classifier_label: str                  # 分类器原始预测
    classifier_conf: float                 # 分类器置信度
    all_probs:       dict[str, float]      # 各类别概率
    llm_triggered:   bool = False          # 是否触发了 LLM
    llm_label:       Optional[str] = None  # LLM 判断结果（触发时有值）
    llm_raw_output:  Optional[str] = None  # LLM 原始输出（调试用）
    category:        str = field(init=False)

    def __post_init__(self):
        self.category = f"{self.main_category}-{self.final_label}"

    def to_dict(self) -> dict:
        return {
            "stt_text":         self.stt_text,
            "main_category":    self.main_category,
            "final_label":      self.final_label,
            "category":         self.category,
            "classifier_label": self.classifier_label,
            "classifier_conf":  round(self.classifier_conf, 6),
            "all_probs":        {k: round(v, 6) for k, v in self.all_probs.items()},
            "llm_triggered":    self.llm_triggered,
            "llm_label":        self.llm_label,
            "llm_raw_output":   self.llm_raw_output,
        }


# ─────────────────────────────────────────────────────────────────────────────
# LLM 封装
# ─────────────────────────────────────────────────────────────────────────────

class _LLMReviewer:
    """
    使用 llama-cpp-python 加载 GGUF 模型，对分类结果进行语义复核。
    线程安全（内置 Lock）。
    """

    # 固定 prompt 骨架大约占 200~400 tokens（系统提示 + 标签描述块）
    # stt_text 截断到此字符数，确保总 prompt 不超过 n_ctx
    _MAX_TEXT_CHARS: int = 800

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_gpu_layers: int = -1,
        temperature: float = 0.1,
        verbose: bool = False,
    ):
        try:
            from llama_cpp import Llama
        except ImportError as e:
            raise RuntimeError(
                "未安装 llama-cpp-python。\n"
                "请在 conda 环境中安装：\n"
                "  CMAKE_ARGS='-DGGML_CUDA=on' "
                "pip install llama-cpp-python==0.3.23 --force-reinstall --no-cache-dir"
            ) from e

        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"GGUF 模型文件不存在: {model_path}")

        self._llm = Llama(
            model_path=model_path,
            chat_format="qwen",
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=verbose,
            flash_attn=True,
        )
        self._temperature = temperature
        self._lock = Lock()

    def _build_prompt(self, messages: list[dict]) -> str:
        """构建 ChatML 格式的 prompt。"""
        chunks = []
        for m in messages:
            role    = m.get("role", "user")
            content = m.get("content", "")
            # 在 user 段注入 /no_think 关闭思维链输出
            if role == "user" and "/no_think" not in content:
                content = "/no_think\n\n" + content
            chunks.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        chunks.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
        return "\n".join(chunks)

    def classify(
        self,
        text: str,
        main_category: str,
        classifier_pred: str,
        valid_labels: list[str],
        all_probs: Optional[dict[str, float]] = None,
    ) -> tuple[str, str]:
        """
        让 LLM 判断正确分类。

        参数
        ----
        all_probs : dict | None
            分类器各类别概率，传入后 prompt 中会展示 top-3 以辅助 LLM 判断。

        返回: (matched_label, raw_output)
          - matched_label: 从 valid_labels 中匹配的标签（匹配失败时返回 classifier_pred）
          - raw_output:    LLM 原始输出文字
        """
        # 截断过长文本，防止 prompt 超出 n_ctx
        text_truncated = text[: self._MAX_TEXT_CHARS]
        if len(text) > self._MAX_TEXT_CHARS:
            text_truncated += "…"

        # 分类器 top-3 预测块
        if all_probs:
            top3 = sorted(all_probs.items(), key=lambda x: -x[1])[:3]
            top3_block = "  " + "／".join(
                f"{lbl}（{prob:.0%}）" for lbl, prob in top3
            )
        else:
            top3_block = f"  {classifier_pred}"

        # 使用关键词规则型提示词（若无对应模板则退回简单格式）
        template = _RULE_PROMPTS.get(main_category)
        if template:
            user_content = template.format(
                text=text_truncated,
                top3_block=top3_block,
            )
        else:
            # 兜底：简单列举标签
            label_list = "、".join(valid_labels)
            user_content = (
                f"【報案原文】\n{text_truncated}\n\n"
                f"【分類器預測】\n{top3_block}\n\n"
                f"【可選類別】{label_list}\n\n"
                "請直接回答類別名稱，禁止輸出其他任何內容。"
            )
        messages = [
            {"role": "system",  "content": _SYSTEM_PROMPT},
            {"role": "user",    "content": user_content},
        ]
        prompt = self._build_prompt(messages)

        try:
            with self._lock:
                result = self._llm.create_completion(
                    prompt=prompt,
                    max_tokens=16,
                    stop=["<|im_end|>", "<|endoftext|>", "\n", "，", "。"],
                    temperature=self._temperature,
                    top_p=0.8,
                    top_k=20,
                    repeat_penalty=1.0,
                )
            raw = (result.get("choices") or [{}])[0].get("text", "").strip()
        except ValueError as e:
            # prompt 仍超出 n_ctx（极少发生），回退到分类器结果
            raw = f"[CONTEXT_OVERFLOW: {e}]"

        matched = _match_label(raw, valid_labels, fallback=classifier_pred)
        return matched, raw


def _match_label(raw: str, valid_labels: list[str], fallback: str) -> str:
    """
    从 LLM 原始输出中匹配最接近的合法标签。
    1. 完全匹配
    2. 子串匹配（raw 包含 label 或 label 包含 raw）
    3. 回退到 fallback
    """
    raw_clean = raw.strip().strip("「」『』【】\"'")

    # 完全匹配
    if raw_clean in valid_labels:
        return raw_clean

    # 子串匹配（精确包含）
    for lbl in valid_labels:
        if lbl in raw_clean or raw_clean in lbl:
            return lbl

    # 去除括号等特殊字符后再次尝试
    raw_simple = re.sub(r"[()（）\s]", "", raw_clean)
    for lbl in valid_labels:
        lbl_simple = re.sub(r"[()（）\s]", "", lbl)
        if lbl_simple in raw_simple or raw_simple in lbl_simple:
            return lbl

    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# 分类器封装
# ─────────────────────────────────────────────────────────────────────────────

class SubCategoryClassifier:
    """
    MacBERT 子类分类器 + LLM 复核。

    参数
    ----
    main_category : str
        主类别名称，如 "救護" 或 "火警"
    model_dir : str
        MacBERT 子类模型目录（含 label_map.json）
    llm_model_path : str | None
        GGUF 模型路径。为 None 时禁用 LLM 复核。
    confidence_threshold : float
        分类器置信度低于此值时才考虑触发 LLM（默认 0.90）。
        设为 1.0 则对所有高频误判类别都触发，无论置信度高低。
    max_len : int
        MacBERT 最大输入长度（与训练时一致）
    device : str | None
        "cuda" / "cpu"，默认自动检测
    llm_n_gpu_layers : int
        LLM GPU 卸载层数，-1 表示全部卸载到 GPU
    llm_verbose : bool
        是否打印 LLM 调试信息

    注意
    ----
    LLM 内部 n_ctx 默认 4096。输入文本超过 800 字符时会自动截断以防止
    prompt 超出上下文窗口；极端情况下仍溢出时会回退到分类器结果。
    """

    def __init__(
        self,
        main_category: str,
        model_dir: str,
        llm_model_path: Optional[str] = None,
        confidence_threshold: float = 1.0,
        max_len: int = 128,
        device: Optional[str] = None,
        llm_n_gpu_layers: int = -1,
        llm_verbose: bool = False,
    ):
        self.main_category        = main_category
        self.confidence_threshold = confidence_threshold
        self.max_len              = max_len
        self.device               = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # 加载 MacBERT 分类器
        label_map_path = os.path.join(model_dir, "label_map.json")
        if not os.path.isfile(label_map_path):
            raise FileNotFoundError(f"label_map.json 不存在: {label_map_path}")
        with open(label_map_path, encoding="utf-8") as f:
            lm = json.load(f)
        self._label2id = lm["label2id"]
        self._id2label = {int(k): v for k, v in lm["id2label"].items()}
        self._valid_labels = [self._id2label[i] for i in range(len(self._id2label))]

        self._tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self._model     = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self._model.eval().to(self.device)

        # LLM 触发集合（当前主类别的高频误判预测标签）
        self._trigger_labels = _LLM_TRIGGER_LABELS.get(main_category, set())

        # 加载 LLM（可选）
        self._llm: Optional[_LLMReviewer] = None
        if llm_model_path:
            self._llm = _LLMReviewer(
                model_path=llm_model_path,
                n_gpu_layers=llm_n_gpu_layers,
                verbose=llm_verbose,
            )

    # ── 内部推理 ──────────────────────────────────────────────────────────────

    def _classifier_infer(
        self, texts: list[str]
    ) -> list[tuple[str, float, dict[str, float]]]:
        """
        批量推理，返回 [(pred_label, confidence, all_probs), ...]。
        """
        inputs = self._tokenizer(
            texts,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_len,
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = self._model(**inputs).logits
        probs_np = torch.softmax(logits, dim=-1).cpu().numpy()

        results = []
        for prob_row in probs_np:
            pred_id = int(np.argmax(prob_row))
            pred_label = self._id2label[pred_id]
            confidence = float(prob_row[pred_id])
            all_probs = {self._id2label[i]: float(prob_row[i]) for i in range(len(prob_row))}
            results.append((pred_label, confidence, all_probs))
        return results

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def predict(self, text: str) -> PredictionResult:
        """对单条文本进行分类（含 LLM 复核）。"""
        results = self.predict_batch([text])
        return results[0]

    def predict_batch(self, texts: list[str]) -> list[PredictionResult]:
        """
        批量分类（含 LLM 复核）。
        分类器阶段全量批次；LLM 阶段仅对触发条件成立的样本逐条调用。
        """
        if not texts:
            return []

        # Step 1: 分类器批量推理
        cls_results = self._classifier_infer(texts)

        # Step 2: 对每条结果判断是否触发 LLM
        # 触发条件：pred_label 属于高频误判集合，且置信度低于阈值
        # 若 confidence_threshold=1.0，则只要在触发集合中就必触发（不看置信度）
        output = []
        for text, (pred_label, conf, all_probs) in zip(texts, cls_results):
            llm_triggered = False
            llm_label     = None
            llm_raw       = None

            if (
                self._llm is not None
                and pred_label in self._trigger_labels
                and conf < self.confidence_threshold
            ):
                llm_triggered = True
                llm_label, llm_raw = self._llm.classify(
                    text=text,
                    main_category=self.main_category,
                    classifier_pred=pred_label,
                    valid_labels=self._valid_labels,
                    all_probs=all_probs,
                )

            final_label = llm_label if (llm_triggered and llm_label) else pred_label

            output.append(PredictionResult(
                stt_text=text,
                main_category=self.main_category,
                final_label=final_label,
                classifier_label=pred_label,
                classifier_conf=conf,
                all_probs=all_probs,
                llm_triggered=llm_triggered,
                llm_label=llm_label,
                llm_raw_output=llm_raw,
            ))

        return output

    @property
    def valid_labels(self) -> list[str]:
        """返回该分类器支持的所有标签列表。"""
        return list(self._valid_labels)

    @property
    def trigger_labels(self) -> set[str]:
        """返回会触发 LLM 复核的预测标签集合。"""
        return set(self._trigger_labels)


# ─────────────────────────────────────────────────────────────────────────────
# 便捷函数：同时管理救護和火警两个分类器
# ─────────────────────────────────────────────────────────────────────────────

class _ClassifierRegistry:
    """懒加载并缓存多个 SubCategoryClassifier 实例。"""

    def __init__(self):
        self._registry: dict[str, SubCategoryClassifier] = {}

    def register(self, classifier: SubCategoryClassifier):
        self._registry[classifier.main_category] = classifier

    def get(self, main_category: str) -> Optional[SubCategoryClassifier]:
        return self._registry.get(main_category)

    def predict(self, text: str, main_category: str) -> Optional[PredictionResult]:
        clf = self.get(main_category)
        if clf is None:
            return None
        return clf.predict(text)


def build_classifiers(
    models_base: str = "/root/autodl-tmp/models/",
    llm_model_path: Optional[str] = "/root/autodl-tmp/models/TW-119-Model/TW-119-Model.gguf",
    confidence_threshold: float = 1.0,
    device: Optional[str] = None,
    llm_n_gpu_layers: int = -1,
    llm_verbose: bool = False,
    enable_llm: bool = True,
) -> _ClassifierRegistry:
    """
    一次性构建救護和火警两个分类器并注册到 registry。

    参数
    ----
    models_base : str
        模型根目录（含 TW-119-BERT-sub_救護/ 和 TW-119-BERT-sub_火警_v2/）
    llm_model_path : str | None
        GGUF 模型路径；设为 None 或 enable_llm=False 时禁用 LLM
    confidence_threshold : float
        置信度阈值，低于此值时触发 LLM 复核
    enable_llm : bool
        是否启用 LLM 复核（方便快速切换纯分类器模式）
    """
    _MODEL_DIRS = {
        "救護": "TW-119-BERT-sub_救護",
        "火警": "TW-119-BERT-sub_火警_v2",
    }
    _llm_path = llm_model_path if enable_llm else None

    registry = _ClassifierRegistry()
    for main_cat, dirname in _MODEL_DIRS.items():
        model_dir = os.path.join(models_base, dirname)
        try:
            clf = SubCategoryClassifier(
                main_category=main_cat,
                model_dir=model_dir,
                llm_model_path=_llm_path,
                confidence_threshold=confidence_threshold,
                device=device,
                llm_n_gpu_layers=llm_n_gpu_layers,
                llm_verbose=llm_verbose,
            )
            registry.register(clf)
            print(f"[build_classifiers] 已加载: {main_cat}  "
                  f"({len(clf.valid_labels)} 类, "
                  f"LLM触发标签: {sorted(clf.trigger_labels)})")
        except Exception as e:
            print(f"[build_classifiers] 跳过 {main_cat}: {e}")

    return registry


def predict_119(
    text: str,
    main_category: str,
    registry: _ClassifierRegistry,
) -> Optional[PredictionResult]:
    """
    便捷函数：对单条文本做子类预测。

    参数
    ----
    text : str
        报案语音转文字
    main_category : str
        已知的主类别（如 "救護" 或 "火警"）
    registry : _ClassifierRegistry
        由 build_classifiers() 创建的分类器注册表

    返回
    ----
    PredictionResult 或 None（若主类别无对应分类器）
    """
    return registry.predict(text, main_category)
