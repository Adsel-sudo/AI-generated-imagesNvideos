from __future__ import annotations

from typing import Any

from .constants import DEFAULT_N_OUTPUTS


SAFE_MODE_KEYWORDS = (
    "婴儿",
    "婴幼儿",
    "宝宝",
    "儿童",
    "小孩",
    "pet",
    "宠物",
    "猫",
    "狗",
)

BACKGROUND_KEYWORDS = (
    "背景",
    "环境",
    "天气",
    "雨",
    "雪",
    "雾",
    "场景",
    "氛围",
    "灯光",
    "天空",
    "室内",
    "室外",
)

STYLE_KEYWORDS = (
    "风格",
    "色调",
    "质感",
    "胶片",
    "插画",
    "写实",
    "赛博",
    "复古",
    "极简",
)


class PromptOptimizer:
    def optimize(
        self,
        *,
        task_type: str,
        raw_request: str,
        references: list[dict[str, Any]],
        usage_options: dict[str, Any],
        generation_targets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        cleaned_request = (raw_request or "").strip()
        if not cleaned_request:
            raise ValueError("raw_request is required")

        normalized_targets = self._normalize_targets(generation_targets)
        safe_mode = self._needs_safe_mode(cleaned_request, references, usage_options)
        style_preference = str(usage_options.get("style_preference") or "").strip()
        requested_size = str(usage_options.get("size") or "").strip()
        reference_breakdown = self._build_reference_breakdown(references)
        continuation_mode = reference_breakdown.get("composition", 0) > 0
        single_frame_constraints = self._build_single_frame_constraints(normalized_targets)

        structured_summary = {
            "task_type": (task_type or "image").strip().lower(),
            "intent": cleaned_request,
            "safe_mode": safe_mode,
            "references": references,
            "reference_breakdown": reference_breakdown,
            "continuation_mode": continuation_mode,
            "usage_options": usage_options,
            "generation_targets": normalized_targets,
            "policy_notes": [
                "PC 和 Mobile 是独立生成目标，不进行裁切复用",
                "电商场景优先保证主体清晰、商品细节完整、关键元素留在安全区域",
            ],
        }

        safety_line = "启用安全风格约束，避免不当内容表达。" if safe_mode else ""
        style_line = f"风格偏好：{style_preference}。" if style_preference else ""
        size_line = f"优先按尺寸 {requested_size} 进行构图与出图。" if requested_size else ""
        reference_role_line = self._build_reference_role_line(reference_breakdown)
        edit_plan = self._build_edit_plan(
            cleaned_request=cleaned_request,
            reference_breakdown=reference_breakdown,
            style_preference=style_preference,
            continuation_mode=continuation_mode,
        )
        continuation_line = (
            "基于参考图所示主体与构图继续优化，仅修改用户本轮指定内容，未提及部分保持上一轮视觉结果一致。"
            if continuation_mode
            else ""
        )
        single_frame_line = " ".join(single_frame_constraints)
        optimized_prompt_cn = (
            f"请根据以下需求生成高质量{'视频' if structured_summary['task_type'] == 'video' else '图片'}素材。\n"
            f"【本轮用户目标】{cleaned_request}\n"
            f"{chr(10).join(edit_plan)}\n"
            f"{reference_role_line}"
            f"{continuation_line}"
            f"{single_frame_line}"
            f"{style_line}"
            f"{size_line}"
            f"{safety_line}"
        ).strip()

        target_lines = []
        for target in normalized_targets:
            dimension = target.get("aspect_ratio") or f"{target.get('width') or '?'}x{target.get('height') or '?'}"
            target_lines.append(f"- {target['target_type']}：{dimension}，生成 {target['n_outputs']} 张")
        reference_lines = self._summarize_references(references)
        reference_section = f"{chr(10).join(reference_lines)}{chr(10)}" if reference_lines else ""

        generation_prompt = (
            f"{optimized_prompt_cn}\n"
            "输出要求：\n"
            f"{chr(10).join(target_lines)}\n"
            f"{reference_section}"
            f"{chr(10).join(f'- {line}' for line in single_frame_constraints)}\n"
            "请确保每个端侧目标独立生成，不共享裁切版本。"
            "当模型无法严格锁定像素尺寸时，至少保持目标宽高比与构图安全边界一致。"
        ).strip()

        normalized_params = {
            "safe_mode": safe_mode,
            "generation_targets": normalized_targets,
            "usage_options": usage_options,
            "references": references,
        }

        return {
            "structured_summary": structured_summary,
            "optimized_prompt_cn": optimized_prompt_cn,
            "generation_prompt": generation_prompt,
            "normalized_params": normalized_params,
        }

    def _normalize_targets(self, generation_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for raw in generation_targets:
            target_type = str(raw.get("target_type") or "other").strip().lower()
            if target_type not in {"pc", "mobile", "image", "other"}:
                target_type = "other"
            normalized.append(
                {
                    "target_type": target_type,
                    "aspect_ratio": raw.get("aspect_ratio"),
                    "width": raw.get("width"),
                    "height": raw.get("height"),
                    "n_outputs": int(raw.get("n_outputs") or DEFAULT_N_OUTPUTS),
                }
            )

        if not normalized:
            normalized.append(
                {
                    "target_type": "pc",
                    "aspect_ratio": "1:1",
                    "width": None,
                    "height": None,
                    "n_outputs": DEFAULT_N_OUTPUTS,
                }
            )

        return normalized

    def _needs_safe_mode(self, raw_request: str, references: list[dict[str, Any]], usage_options: dict[str, Any]) -> bool:
        bag = [raw_request.lower(), str(usage_options).lower(), str(references).lower()]
        combined = "\n".join(bag)
        return any(keyword in combined for keyword in SAFE_MODE_KEYWORDS)

    def _summarize_references(self, references: list[dict[str, Any]]) -> list[str]:
        if not references:
            return []

        counts = self._build_reference_breakdown(references)
        lines = ["参考约束："]
        if counts.get("product", 0):
            lines.append(f"- 商品图: {counts['product']} 张，用于主体保真与关键细节一致。")
        if counts.get("composition", 0):
            lines.append(f"- 元素/构图参考图: {counts['composition']} 张，用于场景、布局、背景关系参考。")
            lines.append("- 基于参考图所示主体与构图继续优化，仅修改用户本轮指定内容。")
        if counts.get("pose", 0):
            lines.append(f"- 姿势参考图: {counts['pose']} 张，用于人物/主体姿态参考。")
        if counts.get("style", 0):
            lines.append(f"- 风格参考图: {counts['style']} 张，用于色调、质感、光影与风格参考。")
        remaining = counts.get("reference", 0)
        if remaining:
            lines.append(f"- 其他参考: {remaining} 张，辅助保持语义一致性。")
        return lines

    def _build_edit_plan(
        self,
        *,
        cleaned_request: str,
        reference_breakdown: dict[str, int],
        style_preference: str,
        continuation_mode: bool,
    ) -> list[str]:
        lowered = cleaned_request.lower()
        has_bg_edit = any(keyword in cleaned_request for keyword in BACKGROUND_KEYWORDS)
        has_style_edit = bool(style_preference) or any(keyword in lowered for keyword in STYLE_KEYWORDS)
        has_product_reference = reference_breakdown.get("product", 0) > 0
        has_composition_reference = reference_breakdown.get("composition", 0) > 0

        subject_keep_line = (
            "【主体保持项】保持主体、主体位置、主体核心特征不变；构图重心与主体识别特征保持连续。"
            if continuation_mode or has_product_reference
            else "【主体保持项】主体清晰可辨，关键细节完整，不出现结构错位。"
        )

        product_lock_line = (
            "【商品图约束】主体保真，避免改变结构、颜色、材质、logo与关键细节。"
            if has_product_reference
            else ""
        )

        background_line = (
            f"【背景/环境修改项】按本轮要求修改背景/天气/环境：{cleaned_request}；未提及元素保持不变。"
            if has_bg_edit
            else "【背景/环境修改项】仅在不影响主体识别的前提下进行必要环境调整。"
        )

        style_line = (
            f"【风格修改项】风格关键词：{style_preference or cleaned_request}；风格表达不得覆盖主体保真要求。"
            if has_style_edit
            else "【风格修改项】维持自然一致的视觉风格，不抢占主体表达。"
        )

        composition_line = (
            "【构图参考项】参考元素/构图参考图中的布局、背景关系和画面组织方式。"
            if has_composition_reference
            else "【构图参考项】保持构图稳定，主体位于安全视觉区域。"
        )

        plan = [subject_keep_line, background_line, style_line, composition_line]
        if product_lock_line:
            plan.insert(1, product_lock_line)
        return plan

    def _build_reference_breakdown(self, references: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in references:
            role = str(item.get("role") or "reference").strip().lower()
            counts[role] = counts.get(role, 0) + 1
        return counts

    def _build_reference_role_line(self, counts: dict[str, int]) -> str:
        lines: list[str] = []
        if counts.get("product", 0):
            lines.append("商品图用于锁定主体形态与细节，不改变主体身份。")
        if counts.get("composition", 0):
            lines.append("元素/构图参考图用于约束场景布局、背景元素和空间关系。")
        if counts.get("pose", 0):
            lines.append("姿势参考图用于保持或迁移主体姿态。")
        if counts.get("style", 0):
            lines.append("风格参考图用于统一视觉风格、色彩与光影。")
        return "".join(lines)

    def _build_single_frame_constraints(self, generation_targets: list[dict[str, Any]]) -> list[str]:
        has_wide_target = any(self._is_wide_target(target) for target in generation_targets)
        lines = [
            "单张图必须是单主体、单场景、单一完整画面，不得在同一张图中拼接多个候选。",
            "禁止拼版图、禁止多宫格、禁止九宫格、禁止多栏排版、禁止分屏对比。",
            "不要在单张图中出现多个相互独立的小图块、小画框或分区画面。",
        ]
        if has_wide_target:
            lines.append("横图比例（如16:9）必须保持单张完整横幅构图，不得把多个场景或多个主体并排拼接在同一张图中。")
        return lines

    def _is_wide_target(self, target: dict[str, Any]) -> bool:
        aspect_ratio = str(target.get("aspect_ratio") or "").strip()
        if ":" in aspect_ratio:
            left, _, right = aspect_ratio.partition(":")
            try:
                width_ratio = float(left.strip())
                height_ratio = float(right.strip())
                return width_ratio > 0 and height_ratio > 0 and (width_ratio / height_ratio) >= 1.3
            except ValueError:
                return False
        width = target.get("width")
        height = target.get("height")
        if isinstance(width, (int, float)) and isinstance(height, (int, float)) and height:
            return (float(width) / float(height)) >= 1.3
        return False


prompt_optimizer = PromptOptimizer()
