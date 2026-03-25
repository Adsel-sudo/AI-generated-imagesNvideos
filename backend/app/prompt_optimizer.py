from __future__ import annotations

from typing import Any


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

        structured_summary = {
            "task_type": (task_type or "image").strip().lower(),
            "intent": cleaned_request,
            "safe_mode": safe_mode,
            "references": references,
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
        optimized_prompt_cn = (
            f"请根据以下需求生成高质量{'视频' if structured_summary['task_type'] == 'video' else '图片'}素材：{cleaned_request}。"
            "场景需突出商品主体，保证主体清晰、细节完整、构图稳定，适合电商展示。"
            "关键元素尽量落在安全区域，避免边缘裁切风险。"
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
            if target_type not in {"pc", "mobile"}:
                target_type = "other"
            normalized.append(
                {
                    "target_type": target_type,
                    "aspect_ratio": raw.get("aspect_ratio"),
                    "width": raw.get("width"),
                    "height": raw.get("height"),
                    "n_outputs": int(raw.get("n_outputs") or 1),
                }
            )

        if not normalized:
            normalized.append({"target_type": "pc", "aspect_ratio": "1:1", "width": None, "height": None, "n_outputs": 1})

        return normalized

    def _needs_safe_mode(self, raw_request: str, references: list[dict[str, Any]], usage_options: dict[str, Any]) -> bool:
        bag = [raw_request.lower(), str(usage_options).lower(), str(references).lower()]
        combined = "\n".join(bag)
        return any(keyword in combined for keyword in SAFE_MODE_KEYWORDS)

    def _summarize_references(self, references: list[dict[str, Any]]) -> list[str]:
        if not references:
            return []

        counts: dict[str, int] = {}
        for item in references:
            role = str(item.get("role") or "reference").strip().lower()
            counts[role] = counts.get(role, 0) + 1

        lines = ["参考约束："]
        for role, count in sorted(counts.items()):
            lines.append(f"- {role}: {count} 张，作为风格/构图/主体一致性参考")
        return lines


prompt_optimizer = PromptOptimizer()
