"""
handlers/火警通用.py
━━━━━━━━━━━━━━━━━━━━
119 SOP — 火警初期研判與四類燃燒標的流程

  run_generic_flow — 初期三題後分流建築物、工廠、車輛、露天野外
  collect_caller_info — 最後確認回撥電話與稱呼
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


def _mentions_smoke(value: Optional[str]) -> bool:
    return any(k in (value or "") for k in ("煙", "烟"))


def _infer_fire_category(burning_object: Optional[str]) -> Optional[str]:
    """LLM 未給標準類別時，以已抽取燃燒物作保守備援。"""
    text = burning_object or ""
    if any(k in text for k in ("工廠", "工厂", "廠房", "厂房")):
        return "工廠"
    if any(k in text for k in ("車", "车", "汽機車", "機車", "机车")):
        return "車輛"
    if any(k in text for k in ("雜草", "杂草", "垃圾", "山林", "森林", "田", "野外")):
        return "露天野外"
    if any(k in text for k in ("房", "住宅", "店面", "大樓", "大楼", "建築", "建筑")):
        return "建築物"
    return None


class HuoJingGenericHandler(SubCategoryHandler):
    """火警大類通用 Handler（依燃燒標的在內部分流）。"""

    def run_generic_flow(self, engine: "SopEngine119") -> None:
        """完成初期研判，再執行對應燃燒標的分支。"""
        engine._ensure_known_fields_from_history()

        self._ask_missing(
            engine, "火警_initial_1", ("fire_or_smoke",),
            "請問現在是看到火，還是只有看到煙，或聞到味道？",
        )
        if _mentions_smoke(engine.case.fire_or_smoke):
            self._ask_missing(
                engine, "火警_initial_smoke_color", ("smoke_color",),
                "是黑煙還是白煙呢？",
            )
        self._ask_missing(
            engine, "火警_initial_2", ("burning_object",),
            "請問是什麼在燒？房子、車子，還是雜草？",
        )
        self._ask_missing(
            engine, "火警_initial_3", ("fire_trend", "fire_extent"),
            "火是越來越大還是消退呢？大概多大範圍？",
        )

        category = engine.case.fire_category or _infer_fire_category(
            engine.case.burning_object
        )
        if category:
            with engine._case_lock:
                engine.case.fire_category = category
                engine.case.sub_category = category
                engine.case.sub_conf = 1.0
            engine._notify_case_update()
        else:
            for _attempt in range(2):
                self._ask_missing(
                    engine, "火警_category", ("fire_category",),
                    "請確認燃燒標的是建築物、工廠、車輛，還是露天野外？",
                )
                category = engine.case.fire_category or _infer_fire_category(
                    engine.case.burning_object
                )
                if category:
                    break
            if category:
                with engine._case_lock:
                    engine.case.fire_category = category
                    engine.case.sub_category = category
                    engine.case.sub_conf = 1.0
                engine._notify_case_update()

        if category == "建築物":
            self._run_building_flow(engine)
        elif category == "工廠":
            self._run_factory_flow(engine)
        elif category == "車輛":
            self._run_vehicle_flow(engine)
        elif category == "露天野外":
            self._run_outdoor_flow(engine)
        else:
            engine._debug_print("fire_category_unresolved", category)
            engine._say("無法確認燃燒標的類別，立即為您轉接專人，請稍候。")
            from sop_119_engine import TransferToHumanError
            raise TransferToHumanError(
                "fire_category_unresolved", result="human_transfer"
            )

    def _ask_missing(
        self,
        engine: "SopEngine119",
        stage: str,
        fields: Iterable[str],
        question: str,
    ) -> Optional[str]:
        """只在任一关联字段未取得时提问，并统一经过 LLM 抽取。"""
        engine._ensure_known_fields_from_history()
        field_tuple = tuple(fields)
        engine._set_stage(stage)
        if all(engine._is_field_filled(field) for field in field_tuple):
            engine._debug_print(
                f"skip_{stage}",
                {field: getattr(engine.case, field) for field in field_tuple},
            )
            return None
        answer = engine._ask_and_extract(question)
        self._check_and_respond_to_triggers(answer, engine)
        return answer

    def _ask_people_trapped(
        self, engine: "SopEngine119", stage: str, question: str
    ) -> None:
        if engine.case.people_trapped is False:
            engine._set_stage(stage)
            return
        fields = (
            ("people_trapped", "trapped_count")
            if engine.case.people_trapped is True
            else ("people_trapped",)
        )
        self._ask_missing(engine, stage, fields, question)
        if engine.case.people_trapped is True and not engine._is_field_filled(
            "trapped_count"
        ):
            self._ask_missing(
                engine, stage, ("trapped_count",), "請問有幾個人受困？"
            )

    def _run_building_flow(self, engine: "SopEngine119") -> None:
        self._ask_missing(
            engine, "火警_building_identity", ("caller_position", "caller_role"),
            "你在裡面還是外面？是住戶、鄰居，還是路過民眾？",
        )
        position = engine.case.caller_position or ""
        if "內" in position or "裡" in position or "里" in position:
            engine._say(
                "請不要往上逃生；若出口有煙火，請關閉房門避難，"
                "移動到外窗並讓消防人員看見你。"
            )
        else:
            engine._say("請不要進入建築物，請在安全位置協助確認現場狀況。")
        self._ask_people_trapped(
            engine, "火警_building_trapped",
            "幫我確認一下，裡面有沒有人？有幾個人？",
        )
        self._ask_missing(
            engine, "火警_building_floors",
            ("building_total_floors", "fire_floor"),
            "建築物總共幾層樓？幾樓在燒？",
        )
        self._ask_missing(
            engine, "火警_building_spread",
            ("fire_spread", "building_layout"),
            "現場有延燒的狀況嗎？是連棟還是頂樓加蓋？",
        )

    def _run_factory_flow(self, engine: "SopEngine119") -> None:
        self._ask_missing(
            engine, "火警_factory_scale", ("factory_scale_type",),
            "是小型工廠、大型鐵皮工廠，還是連棟工廠？",
        )
        self._ask_missing(
            engine, "火警_factory_trapped",
            ("factory_people_present", "people_trapped"),
            "廠內有沒有人？有沒有人受困？",
        )
        if engine.case.people_trapped is True:
            self._ask_missing(
                engine, "火警_factory_trapped", ("trapped_count",),
                "請問有幾個人受困？",
            )
        self._ask_missing(
            engine, "火警_factory_hazard", ("hazardous_materials",),
            "有沒有存放化學品或危險物品？",
        )

    def _run_vehicle_flow(self, engine: "SopEngine119") -> None:
        self._ask_missing(
            engine, "火警_vehicle_detail", ("vehicle_type", "vehicle_count"),
            "車子是什麼車種呢？一台還是多台？",
        )
        fields = (
            ("vehicle_occupants", "vehicle_occupant_count")
            if engine.case.vehicle_occupants is True
            else ("vehicle_occupants",)
        )
        self._ask_missing(
            engine, "火警_vehicle_occupants", fields,
            "車內有沒有人？有幾個人？",
        )
        if engine.case.vehicle_occupants is True and not engine._is_field_filled(
            "vehicle_occupant_count"
        ):
            self._ask_missing(
                engine, "火警_vehicle_occupants", ("vehicle_occupant_count",),
                "請問車內有幾個人？",
            )
        self._ask_missing(
            engine, "火警_vehicle_road", ("road_type",),
            "在一般道路還是高速公路？",
        )

    def _run_outdoor_flow(self, engine: "SopEngine119") -> None:
        self._ask_missing(
            engine, "火警_outdoor_type", ("outdoor_fire_type",),
            "是燒雜草垃圾、山林，還是在高速公路呢？",
        )
        self._ask_missing(
            engine, "火警_outdoor_water", ("nearby_water_source",),
            "現場附近有水源或是消防栓嗎？",
        )
        self._ask_missing(
            engine, "火警_outdoor_threat",
            ("affected_targets", "people_trapped"),
            "有沒有波及到建築物、車輛，或有人受困？",
        )
        outdoor_type = engine.case.outdoor_fire_type or ""
        if any(k in outdoor_type for k in ("雜草", "杂草", "山林", "森林")):
            engine._say(
                "請在安全地點等待並協助引導消防人員，"
                "注意山林或雜草火勢蔓延，不要靠近火場。"
            )

    def _check_and_respond_to_triggers(
        self, caller_text: str, engine: "SopEngine119"
    ) -> None:
        """
        偵測本輪文本中的火警觸發情境 2–14。
        每個情境號只記錄一次；記錄後直接進入下一個問題。
        """
        if not engine._llm or not (caller_text or "").strip():
            return

        try:
            already = list(engine.case.triggered_scenarios)
            new_ids = engine._llm.check_fire_trigger_scenarios(
                caller_text, already_triggered=already,
            )
            engine._debug_print("fire_triggers", {"new": new_ids, "already": already})
        except Exception as e:
            engine._debug_print("fire_triggers_error", e)
            return

        if not new_ids:
            return

        with engine._case_lock:
            for sid in new_ids:
                if sid not in engine.case.triggered_scenarios:
                    engine.case.triggered_scenarios.append(sid)
        engine._notify_case_update()

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """在火災問診末尾確認回撥電話與報案人稱呼。"""
        from sop_119_engine import TransferToHumanError
        from sop_utils_119 import parse_yes_no_for_question

        engine._set_stage("火警_caller_info")
        engine._ensure_known_fields_from_history()
        original_contact = engine.case.caller_contact
        if original_contact:
            question = (
                f"最後和您確認一下，聯絡電話是 {original_contact} 嗎？"
                "是先生還是小姐呢？"
            )
        else:
            question = "最後請提供回撥電話，並告訴我是先生還是小姐。"
        answer = engine._ask_and_extract(question)
        self._extract_caller_info(answer, question, engine)

        if original_contact:
            confirmed = parse_yes_no_for_question(question, answer)
            if confirmed is False and engine.case.caller_contact == original_contact:
                correction_q = "請重新提供正確的回撥電話。"
                correction = engine._ask_and_extract(correction_q)
                self._extract_caller_info(correction, correction_q, engine)

        while not engine._is_field_filled("caller_contact"):
            phone_q = "請提供可以回撥的聯絡電話。"
            phone_answer = engine._ask_and_extract(phone_q)
            self._extract_caller_info(phone_answer, phone_q, engine)
        while not engine._is_field_filled("caller_salutation"):
            salutation_q = "請問是先生還是小姐？"
            salutation_answer = engine._ask_and_extract(salutation_q)
            self._extract_caller_info(salutation_answer, salutation_q, engine)

        if not engine.case.caller_contact or not engine.case.caller_salutation:
            engine._say("無法確認報案人資訊，立即為您轉接專人，請稍候。")
            raise TransferToHumanError("caller_info_missing", result="human_transfer")

        engine._say(
            f"聯絡電話：{engine.case.caller_contact}，"
            f"稱呼：{engine.case.caller_salutation}，已為您記錄。"
        )

        engine._say("請在現場耐心等待，確認入口通暢，並引導消防人員，謝謝。")
        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})

    @staticmethod
    def _extract_caller_info(
        caller_text: str, question: str, engine: "SopEngine119"
    ) -> None:
        if not engine._llm or not caller_text.strip():
            return
        try:
            ci = engine._llm.extract_caller_info(
                question, caller_text, include_address=False
            )
            engine._debug_print("caller_info", ci)
        except Exception as exc:
            engine._debug_print("caller_info_error", exc)
            return
        with engine._case_lock:
            if ci.get("caller_name"):
                engine.case.caller_name = ci["caller_name"]
            if ci.get("caller_contact"):
                engine.case.caller_contact = ci["caller_contact"]
            if ci.get("caller_salutation") in ("先生", "小姐"):
                engine.case.caller_salutation = ci["caller_salutation"]
        engine._notify_case_update()
