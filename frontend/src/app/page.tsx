"use client";

import { useMemo, useState } from "react";
import { generateImageTask, optimizePrompt } from "@/src/lib/api/image";

type SizeOption = "1600x1600" | "1464x600" | "600x450" | "other";

export default function ImageWorkbenchPage() {
  const [requestText, setRequestText] = useState("");
  const [stylePreference, setStylePreference] = useState("");
  const [selectedSize, setSelectedSize] = useState<SizeOption>("1600x1600");
  const [customSize, setCustomSize] = useState("");
  const [optimizeLoading, setOptimizeLoading] = useState(false);
  const [optimizeError, setOptimizeError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [mergedPrompt, setMergedPrompt] = useState("");
  const [hasMerged, setHasMerged] = useState(false);

  const resolvedSizeText = useMemo(() => {
    if (selectedSize === "1600x1600") return "1600 × 1600";
    if (selectedSize === "1464x600") return "1464 × 600";
    if (selectedSize === "600x450") return "600 × 450";
    return customSize.trim() ? customSize.trim() : "（未填写）";
  }, [customSize, selectedSize]);

  const finalSizeValue = useMemo(() => {
    if (selectedSize === "other") return customSize.trim();
    return selectedSize;
  }, [customSize, selectedSize]);

  const buildTargetsFromSize = (size: string) => {
    if (!size) return [];
    return [
      {
        type: "custom",
        aspect_ratio: size,
      },
    ];
  };

  const handleOptimizePrompt = async () => {
    if (!requestText.trim()) {
      setOptimizeError("请先填写原始需求");
      return;
    }

    setOptimizeLoading(true);
    setOptimizeError(null);

    try {
      const res = await optimizePrompt({
        request_text: requestText.trim(),
        targets: buildTargetsFromSize(finalSizeValue),
        usage_options: {},
        style_preference: stylePreference.trim(),
        references: [],
      });

      // 把汇总后的中文提示词写入可编辑区
      setMergedPrompt(res.optimized_prompt_cn ?? "");
      setHasMerged(true);
    } catch (e) {
      const message =
        e instanceof Error ? e.message : "优化失败，请稍后重试。";
      setOptimizeError(message);
    } finally {
      setOptimizeLoading(false);
    }
  };

  const handleSubmitTask = async () => {
    // hasMerged=false 或 mergedPrompt 为空白时，直接使用原始需求
    const shouldUseOriginal = !hasMerged || !mergedPrompt.trim().length;
    const usedPrompt = shouldUseOriginal ? requestText.trim() : mergedPrompt;

    if (!usedPrompt) {
      setOptimizeError("请先填写原始需求");
      return;
    }

    setIsSubmitting(true);
    setOptimizeError(null);

    try {
      await generateImageTask({
        request_text: usedPrompt,
        targets: buildTargetsFromSize(finalSizeValue),
        usage_options: {},
        style_preference: stylePreference.trim(),
        references: [],
      });
    } catch (e) {
      const message =
        e instanceof Error ? e.message : "任务提交失败，请稍后重试。";
      setOptimizeError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-dvh bg-gradient-to-b from-slate-50 via-slate-50 to-slate-100/70 px-4 py-6 sm:px-6 sm:py-10">
      <div className="mx-auto w-full max-w-6xl">
        <div className="grid gap-6 lg:grid-cols-[460px_1fr]">
          {/* 左侧：输入区 */}
          <section className="rounded-2xl border border-slate-200/70 bg-white/80 p-5 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-white/70">
            <div className="space-y-5">
              <div>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="text-base font-semibold text-slate-900">原始需求</div>
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                      必填
                    </span>
                  </div>
                </div>
                <textarea
                  className="mt-2 w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-4 focus:ring-slate-200"
                  rows={8}
                  value={requestText}
                  onChange={(e) => setRequestText(e.target.value)}
                />
              </div>

              <div>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="text-base font-semibold text-slate-900">参考图片</div>
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                      选填
                    </span>
                  </div>
                  <div className="text-xs text-slate-400">最多上传 8 张，后续支持上传与预览</div>
                </div>

                <div className="mt-2 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-4">
                    <div className="text-sm font-medium text-slate-900">商品图</div>
                    <div className="mt-1 text-xs text-slate-500">上传占位（暂不支持真实上传）</div>
                    <div className="mt-3 h-16 rounded-lg border border-dashed border-slate-200 bg-white/60" />
                  </div>

                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-4">
                    <div className="text-sm font-medium text-slate-900">元素/构图参考图</div>
                    <div className="mt-1 text-xs text-slate-500">上传占位（暂不支持真实上传）</div>
                    <div className="mt-3 h-16 rounded-lg border border-dashed border-slate-200 bg-white/60" />
                  </div>

                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-4">
                    <div className="text-sm font-medium text-slate-900">姿势参考图</div>
                    <div className="mt-1 text-xs text-slate-500">上传占位（暂不支持真实上传）</div>
                    <div className="mt-3 h-16 rounded-lg border border-dashed border-slate-200 bg-white/60" />
                  </div>

                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-4">
                    <div className="text-sm font-medium text-slate-900">风格参考图</div>
                    <div className="mt-1 text-xs text-slate-500">上传占位（暂不支持真实上传）</div>
                    <div className="mt-3 h-16 rounded-lg border border-dashed border-slate-200 bg-white/60" />
                  </div>
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <div className="text-base font-semibold text-slate-900">尺寸选择</div>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                    选填
                  </span>
                </div>
                <div className="mt-2 space-y-2">
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="radio"
                      name="size"
                      className="h-4 w-4 border-slate-300 text-slate-900 focus:ring-slate-400"
                      checked={selectedSize === "1600x1600"}
                      onChange={() => setSelectedSize("1600x1600")}
                    />
                    1600 × 1600
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="radio"
                      name="size"
                      className="h-4 w-4 border-slate-300 text-slate-900 focus:ring-slate-400"
                      checked={selectedSize === "1464x600"}
                      onChange={() => setSelectedSize("1464x600")}
                    />
                    1464 × 600
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="radio"
                      name="size"
                      className="h-4 w-4 border-slate-300 text-slate-900 focus:ring-slate-400"
                      checked={selectedSize === "600x450"}
                      onChange={() => setSelectedSize("600x450")}
                    />
                    600 × 450
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="radio"
                      name="size"
                      className="h-4 w-4 border-slate-300 text-slate-900 focus:ring-slate-400"
                      checked={selectedSize === "other"}
                      onChange={() => setSelectedSize("other")}
                    />
                    其他
                  </label>

                  {selectedSize === "other" ? (
                    <input
                      className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-4 focus:ring-slate-200"
                      placeholder="例如：1200 × 628"
                      value={customSize}
                      onChange={(e) => setCustomSize(e.target.value)}
                    />
                  ) : null}
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <div className="text-base font-semibold text-slate-900">风格倾向</div>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                    选填
                  </span>
                </div>
                <input
                  className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-slate-200 placeholder:text-slate-400 focus:ring-4 focus:ring-slate-200"
                  placeholder="例：清爽、明亮、度假感、夏日氛围、适合电商展示"
                  value={stylePreference}
                  onChange={(e) => setStylePreference(e.target.value)}
                />
              </div>
            </div>
          </section>

          {/* 右侧：结果区 */}
          <section className="grid gap-5">
            {/* 需求汇总模块（与生成结果同级，放在上方） */}
            <div className="rounded-2xl border border-slate-200/70 bg-white/80 p-5 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-white/70">
              <div className="flex items-center justify-between gap-3">
                <button
                  type="button"
                  className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-900 shadow-sm hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-slate-200"
                  onClick={handleOptimizePrompt}
                  disabled={optimizeLoading}
                >
                  {optimizeLoading ? "汇总中..." : "👉 需求汇总"}
                </button>
                <button
                  type="button"
                  className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-slate-200 disabled:cursor-not-allowed disabled:bg-slate-600"
                  onClick={handleSubmitTask}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "任务生成中..." : "提交任务"}
                </button>
              </div>

              {optimizeError ? (
                <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {optimizeError}
                </div>
              ) : null}

              <textarea
                className="mt-3 min-h-[160px] w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-slate-200 focus:ring-4 focus:ring-slate-200"
                value={mergedPrompt}
                onChange={(e) => setMergedPrompt(e.target.value)}
                placeholder={`点击『需求汇总』后，将整合原始需求、参考图片、尺寸选择和风格倾向生成完整描述。\n如果不点击汇总，将直接使用原始需求生成图片。\n你也可以在此基础上手动修改。`}
              />
            </div>

            {/* 生成结果模块 */}
            <div className="rounded-2xl border border-slate-200/70 bg-white/80 p-5 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-white/70">
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="text-base font-semibold text-slate-900">生成结果</h2>
                <div className="text-sm text-gray-500">
                  当前模型：Nano Banana 2
                  {/* 实际模型为 gemini-3.1-flash-image-preview，仅用于展示友好名称 */}
                </div>
              </div>

              <div className="mt-4">
                <div className="aspect-[4/3] w-full rounded-xl border border-dashed border-slate-200 bg-slate-50/70" />
                <div className="mt-2 text-xs text-slate-500">
                  （占位：后续展示生成图片列表、参数与选中状态；当前尺寸：{resolvedSizeText}）
                </div>
                {/* 未来：每张生成图旁边会有单独下载按钮；当多选图片时，默认下载 zip */}
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

